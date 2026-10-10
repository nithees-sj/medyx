"""Stage 2: AI extraction, with the DEMO_CACHE safety net (spec §7.8)."""

import logging

from app.ai import client as ai
from app.config import get_settings
from app.services.ingest.schemas import ExtractionResult

log = logging.getLogger(__name__)


class ExtractionFailed(Exception):
    """Extraction failed and no cached result exists. Message is safe to show the user."""


INSTRUCTION = (
    "Extract this medical document into the schema. Copy names, values and units exactly as printed; "
    "give page numbers, short verbatim snippets and honest confidence for every item."
)


async def extract_document(data: bytes, mime: str, sha256: str) -> tuple[ExtractionResult, str]:
    """Return (result, source) where source is "ai" or "cache".

    After every successful AI extraction the raw JSON is saved to demo_cache/<sha256>.json.
    If the AI call fails and DEMO_CACHE=true, a cached result is used, but only for files
    whose hash is already cached. Unknown files fail visibly.
    """
    s = get_settings()
    cache_path = s.demo_cache_dir / f"{sha256}.json"
    try:
        result = await ai.generate_structured(
            purpose="extract",
            system=ai.load_prompt("extraction"),
            contents=[ai.file_part(data, mime), INSTRUCTION],
            schema=ExtractionResult,
            thinking="low",
            max_quota_wait=120,
        )
    except ai.AIError as e:
        if s.demo_cache and cache_path.exists():
            log.warning("extraction failed (%s); using DEMO_CACHE for %s", e, sha256[:12])
            return ExtractionResult.model_validate_json(cache_path.read_text(encoding="utf-8")), "cache"
        raise ExtractionFailed(f"Couldn't read this document: {e}") from e

    s.demo_cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(result.model_dump_json(indent=1), encoding="utf-8")
    return result, "ai"
