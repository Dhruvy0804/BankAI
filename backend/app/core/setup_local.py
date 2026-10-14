"""Create an ignored local configuration without printing its random secret."""

import secrets

from app.core.config import ROOT


def main():
    target = ROOT / ".env"
    template = (ROOT / ".env.example").read_text(encoding="utf-8")
    try:
        with target.open("x", encoding="utf-8") as stream:
            stream.write(
                template.replace(
                    "replace-with-a-long-random-local-secret", secrets.token_urlsafe(48)
                )
            )
    except FileExistsError:
        raise SystemExit(
            ".env already exists; preserved. Configure APP_SECRET_KEY there if needed."
        ) from None
    print("Created ignored local .env with a random signing key. No secret was printed.")


if __name__ == "__main__":
    main()
