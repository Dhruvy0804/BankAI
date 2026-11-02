"""Approved fictional policy ingestion and bounded semantic retrieval."""

import hashlib
import math
import re
from collections import defaultdict
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from google import genai
from google.genai import types
from pydantic import Field
from sqlalchemy import func, select, text

from app.agents.guardrails import INSTRUCTION_ATTACK
from app.core.config import ROOT, Settings
from app.core.errors import APIError
from app.db.session import build_engine
from app.models import PolicyChunk, PolicyDocument
from app.schemas import Input

POLICY_DIR = ROOT / "data" / "banking_policies"
APPROVED_FILES = ("demo_loans.md", "demo_cards.md", "demo_accounts_support.md")
DIMENSIONS = 768
MIN_SIMILARITY = 0.60
UNSAFE_TEXT = re.compile(r"<\s*(?:script|iframe)\b", re.IGNORECASE)


def policy_question(value):
    return bool(
        re.search(
            r"\b(?:polic(?:y|ies)|fees?|documents?)\b|\b(?:kyc|eligibility|loan)\s+(?:rules|requirements)\b",
            value,
            re.IGNORECASE,
        )
    )


class PolicyQuery(Input):
    query: str = Field(min_length=3, max_length=600, pattern=r"\S")


class PolicySource(Input):
    citation_id: str = Field(pattern=r"^P-[0-9a-f-]{36}$")
    document_id: UUID
    chunk_id: UUID
    title: str = Field(max_length=200)
    source: str = Field(max_length=255)
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    section: str = Field(max_length=200)
    excerpt: str = Field(max_length=1600)
    similarity: float = Field(ge=-1, le=1, allow_inf_nan=False)


class PolicySearch(Input):
    status: Literal["found", "missing", "conflict"]
    sources: list[PolicySource] = Field(default_factory=list, max_length=4)
    embedding_model: str
    embedding_tokens: int | None = Field(default=None, ge=0)


def chunks(markdown):
    """Each short, named section is one citation unit; reject oversized source edits."""
    if INSTRUCTION_ATTACK.search(markdown) or UNSAFE_TEXT.search(markdown):
        raise ValueError(
            "Policy contains instruction-like or executable text; operator review required"
        )
    title, section, lines = "", "", []
    result = []
    for line in markdown.splitlines() + ["## END"]:
        if line.startswith("# "):
            title = line[2:].strip()
        elif line.startswith("## "):
            body = "\n".join(lines).strip()
            if body:
                if not section or len(body) > 1600:
                    raise ValueError("Policies require named sections of at most 1600 characters")
                result.append((section, body))
            section, lines = line[3:].strip(), []
        else:
            lines.append(line)
    if not title or not result or len(title) > 200:
        raise ValueError("Policy title and sections are required")
    if len({section.casefold() for section, _ in result}) != len(result):
        raise ValueError("Policy section names must be unique within a document")
    return title, result


def corpus():
    approved = []
    for name in APPROVED_FILES:
        raw = (POLICY_DIR / name).read_text(encoding="utf-8")
        title, parts = chunks(raw)
        approved.append((name, hashlib.sha256(raw.encode()).hexdigest(), title, parts))
    return approved


def normalize_vector(values):
    if len(values) != DIMENSIONS or any(not math.isfinite(v) for v in values):
        raise ValueError("Invalid embedding dimensions or values")
    norm = math.sqrt(sum(v * v for v in values))
    if not math.isfinite(norm) or norm == 0:
        raise ValueError("Invalid embedding norm")
    return [v / norm for v in values]


def embed(settings, texts, task_type):
    if not settings.embedding_configured:
        raise APIError(503, "EMBEDDING_NOT_CONFIGURED", "Configure policy embeddings first.")
    try:
        with genai.Client(
            api_key=settings.embedding_key.get_secret_value(),
            http_options=types.HttpOptions(
                timeout=20000, retry_options=types.HttpRetryOptions(attempts=1)
            ),
        ) as client:
            result = client.models.embed_content(
                model=settings.embedding_model,
                contents=texts,
                config=types.EmbedContentConfig(
                    task_type=task_type, output_dimensionality=DIMENSIONS
                ),
            )
        if not result.embeddings or len(result.embeddings) != len(texts):
            raise ValueError("Embedding response count mismatch")
        vectors = [normalize_vector(row.values or []) for row in result.embeddings]
        # Never infer token usage when the provider omits it.
        usage = getattr(result, "usage_metadata", None)
        tokens = getattr(usage, "total_token_count", None)
        return vectors, tokens
    except Exception as exc:
        raise APIError(
            503, "EMBEDDING_UNAVAILABLE", "Policy search is temporarily unavailable."
        ) from exc


def ingest(factory, settings):
    """Explicit operator command; never embeds automatically on startup or customer requests."""
    if not settings.embedding_configured:
        raise APIError(503, "EMBEDDING_NOT_CONFIGURED", "Configure policy embeddings first.")
    approved = corpus()
    pending = []
    with factory() as db:
        for name, checksum, title, parts in approved:
            for index, (section, body) in enumerate(parts):
                identifier = uuid5(NAMESPACE_URL, f"bankai-policy/{name}/{checksum}/{index}")
                row = db.get(PolicyChunk, identifier)
                if (
                    row is None
                    or row.embedding_model != settings.embedding_model
                    or row.embedding is None
                    or len(row.embedding) != DIMENSIONS
                    or row.text != body
                    or row.section != section
                ):
                    pending.append((name, checksum, title, index, section, body, identifier))
    if not pending:
        return {"embedded_chunks": 0, "embedding_tokens": 0}
    vectors, tokens = embed(
        settings, [f"{r[2]}\n{r[4]}\n{r[5]}" for r in pending], "RETRIEVAL_DOCUMENT"
    )
    with factory() as db, db.begin():
        db.execute(text("SELECT pg_advisory_xact_lock(2026102107)"))
        for row, vector in zip(pending, vectors, strict=True):
            name, checksum, title, index, section, body, identifier = row
            document = db.scalar(
                select(PolicyDocument).where(
                    PolicyDocument.source == name, PolicyDocument.checksum == checksum
                )
            )
            if document is None:
                document = PolicyDocument(title=title, source=name, checksum=checksum)
                db.add(document)
                db.flush()
            document.title = title
            chunk = db.get(PolicyChunk, identifier)
            if chunk is None:
                chunk = PolicyChunk(id=identifier, document_id=document.id, chunk_index=index)
                db.add(chunk)
            chunk.text, chunk.section = body, section
            chunk.embedding, chunk.embedding_model = vector, settings.embedding_model
    return {"embedded_chunks": len(pending), "embedding_tokens": tokens}


def retrieve(db, settings, query):
    query = PolicyQuery(query=query).query
    approved = corpus()
    # Only exact checked-in source versions qualify. Old versions and arbitrary DB rows do not.
    allowed = {(name, checksum): (title, parts) for name, checksum, title, parts in approved}
    rows = list(
        db.execute(
            select(PolicyDocument, PolicyChunk)
            .join(PolicyChunk)
            .where(
                PolicyDocument.source.in_(APPROVED_FILES),
                PolicyChunk.embedding_model == settings.embedding_model,
                func.vector_dims(PolicyChunk.embedding) == DIMENSIONS,
            )
        )
    )
    trusted = []
    for document, chunk in rows:
        current = allowed.get((document.source, document.checksum))
        if current is None:
            continue
        title, parts = current
        if (
            document.title != title
            or chunk.chunk_index >= len(parts)
            or (chunk.section, chunk.text) != parts[chunk.chunk_index]
        ):
            raise APIError(503, "POLICY_INTEGRITY", "The policy index needs operator review.")
        try:
            normalize_vector(chunk.embedding)
        except ValueError as exc:
            raise APIError(
                503, "POLICY_INTEGRITY", "The policy index needs operator review."
            ) from exc
        trusted.append((document, chunk))
    if len(trusted) != sum(len(parts) for _, _, _, parts in approved):
        raise APIError(503, "POLICY_INDEX_NOT_READY", "Ingest the approved policy corpus first.")
    vectors, tokens = embed(settings, [query], "RETRIEVAL_QUERY")
    ids = [chunk.id for _, chunk in trusted]
    # Exact pgvector scan is sufficient for this small, fixed demo corpus.
    distances = dict(
        db.execute(
            select(PolicyChunk.id, PolicyChunk.embedding.cosine_distance(vectors[0])).where(
                PolicyChunk.id.in_(ids)
            )
        ).all()
    )
    matches = sorted(
        [(1 - distances[chunk.id], document, chunk) for document, chunk in trusted],
        key=lambda item: (-item[0], str(item[2].id)),
    )
    # shortcut: conflicts use equal section names; review semantic contradictions when corpus expands.
    sections = defaultdict(set)
    for _, chunk in trusted:
        sections[chunk.section.casefold()].add(chunk.text.strip())
    found = [row for row in matches if row[0] >= MIN_SIMILARITY][:4]
    conflict = any(len(sections[chunk.section.casefold()]) > 1 for _, _, chunk in found)
    if conflict:
        # Keep both sides visible instead of selecting a policy by score or ingestion date.
        names = {
            chunk.section.casefold()
            for _, _, chunk in found
            if len(sections[chunk.section.casefold()]) > 1
        }
        found = [row for row in matches if row[2].section.casefold() in names][:4]
    sources = [
        PolicySource(
            citation_id=f"P-{chunk.id}",
            document_id=document.id,
            chunk_id=chunk.id,
            title=document.title,
            source=document.source,
            checksum=document.checksum,
            section=chunk.section,
            excerpt=chunk.text,
            similarity=max(-1, min(1, score)),
        )
        for score, document, chunk in found
    ]
    return PolicySearch(
        status="conflict" if conflict else "found" if sources else "missing",
        sources=sources,
        embedding_model=settings.embedding_model,
        embedding_tokens=tokens,
    )


def policy_sources(facts):
    return {
        source.citation_id: source
        for fact in facts
        if fact.tool == "search_policies"
        for source in PolicySearch.model_validate(fact.data).sources
    }


def validate_citations(answer, facts, *, required=False):
    available = policy_sources(facts)
    if set(answer.source_ids) - available.keys():
        raise ValueError("Citations must reference retrieved policy sources only")
    markers = set(re.findall(r"\[(P-[^\]\s]+)\]", answer.answer))
    if markers - set(answer.source_ids):
        raise ValueError("Answer citation markers must match selected sources")
    searches = [PolicySearch.model_validate(f.data) for f in facts if f.tool == "search_policies"]
    if required and answer.status == "answered" and not searches:
        raise ValueError("Policy questions require search_policies evidence")
    if searches and answer.status == "answered":
        if any(search.status != "found" for search in searches):
            raise ValueError("Missing or conflicting policies require needs_tools or clarification")
        if not answer.source_ids:
            raise ValueError("A policy answer requires retrieved source_ids")


def main():
    import json

    from sqlalchemy.orm import sessionmaker

    settings = Settings()
    engine = build_engine(settings)
    try:
        print(json.dumps(ingest(sessionmaker(engine), settings)))
    except APIError as exc:
        raise SystemExit(f"{exc.code}: {exc.message}") from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
