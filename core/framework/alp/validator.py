"""ALP card validator — validates a card dict against the ALP JSON schema (v0.9.0)."""

import logging
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

ALP_SCHEMA_URL = (
    "https://raw.githubusercontent.com/RodrigoMvs123/agent-load-protocol"
    "/main/schema/agent.alp.schema.json"
)

_schema_cache: dict | None = None


def _fetch_schema() -> dict:
    """Fetch the ALP JSON schema from GitHub (cached after first call)."""
    global _schema_cache
    if _schema_cache is not None:
        return _schema_cache

    import json

    try:
        req = urllib.request.Request(ALP_SCHEMA_URL, headers={"User-Agent": "Hive/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            _schema_cache = json.loads(resp.read().decode("utf-8"))
            logger.debug("ALP schema fetched from %s", ALP_SCHEMA_URL)
            return _schema_cache
    except Exception as e:
        raise RuntimeError(
            f"Failed to fetch ALP schema from {ALP_SCHEMA_URL}: {e}\n"
            "Check your internet connection or set a local schema path."
        ) from e


def validate_alp_card(card: dict[str, Any]) -> bool:
    """Validate a card dict against the ALP v0.2.2 JSON schema.

    Args:
        card: The ALP card dict to validate.

    Returns:
        True if valid.

    Raises:
        ValueError: With a clear message listing all validation errors.
        RuntimeError: If the schema cannot be fetched.
    """
    try:
        import jsonschema
    except ImportError as e:
        raise ImportError(
            "jsonschema is required for ALP validation. "
            "Install it with: uv pip install jsonschema"
        ) from e

    schema = _fetch_schema()
    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(card), key=lambda e: list(e.path))

    if errors:
        messages = "\n".join(
            f"  - {'.'.join(str(p) for p in e.path) or '<root>'}: {e.message}"
            for e in errors
        )
        raise ValueError(f"ALP card validation failed:\n{messages}")

    logger.info("ALP card '%s' is valid (alp_version=%s)", card.get("id"), card.get("alp_version"))
    return True
