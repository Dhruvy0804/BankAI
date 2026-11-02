"""Small, deterministic checks at untrusted text and tool boundaries."""

import re

INSTRUCTION_ATTACK = re.compile(
    r"\b(?:ignore|disregard|override)\s+(?:all\s+)?(?:previous|prior|system|developer)\s+(?:instructions|rules|prompts|messages)\b"
    r"|\b(?:reveal|print|show|expose|give\s+me)\b.{0,40}\b(?:system prompt|developer prompt|api key|secret key|access token|passwords?|chain of thought)\b"
    r"|\b(?:bypass|disable|skip)\b.{0,40}\b(?:confirmation|authorization|guardrails?|safety checks?)\b"
    r"|<\s*/?\s*(?:system|developer|assistant)\s*>"
    r"|\[\s*(?:system|developer|inst)\s*\]"
    r"|\b(?:act as|you are now)\s+(?:the\s+)?(?:system|developer)\b",
    re.IGNORECASE,
)
DIRECT_ABUSE = re.compile(r"\byou(?:'re| are) (?:an? )?(?:idiot|moron)\b", re.IGNORECASE)
BLOCK_CLAIM = re.compile(
    r"\b(?:i\s+(?:have\s+)?blocked|(?:your|the)\s+card\s+(?:has been|was|is now)\s+blocked)\b",
    re.IGNORECASE,
)
LOAN_CLAIM = re.compile(
    r"\b(?:i\s+(?:have\s+)?(?:submitted|approved)|(?:your|the)\s+loan\s+application\s+(?:has been|was|is now)\s+(?:submitted|approved))\b",
    re.IGNORECASE,
)


def unsafe_request(text: str) -> bool:
    return bool(INSTRUCTION_ATTACK.search(text) or DIRECT_ABUSE.search(text))


def filter_attack_history(history: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [
        item
        for index in range(0, len(history) - 1, 2)
        if not unsafe_request(history[index][1])
        for item in history[index : index + 2]
    ]


def validate_prepared_action_claims(answer: str, tools: set[str]) -> None:
    if "prepare_card_block" in tools and BLOCK_CLAIM.search(answer):
        raise ValueError("A prepared card block must not be described as completed")
    if "prepare_loan_application" in tools and LOAN_CLAIM.search(answer):
        raise ValueError(
            "A prepared loan application must not be described as submitted or approved"
        )
