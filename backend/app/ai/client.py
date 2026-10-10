"""The only module that calls the AI model (Google Gemini; see docs/DECISIONS.md D2).

- Structured output: JSON schema from a Pydantic model, validated on return; on a
  validation failure we retry once with the error, then fail visibly.
- Logs purpose, model, latency and token counts. Never logs prompts or outputs (PHI).
"""

import asyncio
import functools
import json
import logging
import re
import time
from collections import deque
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any, TypeVar, cast

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, ValidationError

from app.config import get_settings

log = logging.getLogger("healththread.ai")

PROMPTS_DIR = Path(__file__).parent / "prompts"
T = TypeVar("T", bound=BaseModel)
Content = str | types.Part | types.Content


class AIError(RuntimeError):
    """The model call failed or returned something unusable. Message is safe to show users."""


class AINotConfigured(AIError):
    pass


class _RateLimiter:
    """Sliding-window limiter shared by every AI call in this process.

    Keeps us under the key's requests-per-minute quota (the free Gemini tier allows 5),
    so bursts (e.g. nine uploads at once) queue up instead of failing with 429.
    """

    def __init__(self) -> None:
        self._calls: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        rpm = max(1, get_settings().ai_requests_per_minute)
        async with self._lock:
            while True:
                now = time.monotonic()
                while self._calls and now - self._calls[0] >= 60:
                    self._calls.popleft()
                if len(self._calls) < rpm:
                    self._calls.append(now)
                    return
                await asyncio.sleep(60 - (now - self._calls[0]) + 0.1)


_limiter = _RateLimiter()


def _retry_delay_seconds(err: genai_errors.APIError) -> float | None:
    """Google puts a RetryInfo.retryDelay like '42s' in 429 responses."""
    try:
        for d in (err.details or {}).get("error", {}).get("details", []):
            if d.get("@type", "").endswith("RetryInfo"):
                m = re.match(r"([\d.]+)s", d.get("retryDelay", ""))
                if m:
                    return float(m.group(1))
    except AttributeError:
        pass
    return None


@functools.cache
def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


@functools.cache
def _client() -> genai.Client:
    s = get_settings()
    if not s.gemini_api_key:
        raise AINotConfigured("AI is not configured (GEMINI_API_KEY is empty)")
    return genai.Client(
        api_key=s.gemini_api_key,
        http_options=types.HttpOptions(
            timeout=int(s.ai_timeout_seconds * 1000),
            # 429s are handled in _generate (honouring Google's retryDelay); transient 5xx retried here.
            retry_options=types.HttpRetryOptions(attempts=3, http_status_codes=[500, 502, 503, 504]),
        ),
    )


def file_part(data: bytes, mime_type: str) -> types.Part:
    return types.Part.from_bytes(data=data, mime_type=mime_type)


def _config(
    system: str | None,
    *,
    thinking: str,
    temperature: float | None,
    max_output_tokens: int,
    schema: type[BaseModel] | None = None,
    tools: list[types.Tool] | None = None,
) -> types.GenerateContentConfig:
    cfg: dict[str, Any] = {
        "system_instruction": system,
        "thinking_config": types.ThinkingConfig(thinking_level=thinking),
        "max_output_tokens": max_output_tokens,
    }
    if temperature is not None:
        cfg["temperature"] = temperature
    if schema is not None:
        cfg["response_mime_type"] = "application/json"
        cfg["response_json_schema"] = schema.model_json_schema()
    if tools:
        cfg["tools"] = tools
        cfg["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(disable=True)
    return types.GenerateContentConfig(**cfg)


def _log_usage(
    purpose: str, started: float, resp: types.GenerateContentResponse | None, ok: bool, model: str | None = None
) -> None:
    u = resp.usage_metadata if resp is not None else None
    log.info(
        "ai purpose=%s model=%s ok=%s ms=%d in=%s out=%s thought=%s",
        purpose,
        model or get_settings().gemini_model,
        ok,
        (time.monotonic() - started) * 1000,
        getattr(u, "prompt_token_count", None),
        getattr(u, "candidates_token_count", None),
        getattr(u, "thoughts_token_count", None),
    )


def _check_finish(resp: types.GenerateContentResponse) -> None:
    if resp.prompt_feedback and resp.prompt_feedback.block_reason:
        raise AIError(f"The AI declined this request ({resp.prompt_feedback.block_reason})")
    cand = resp.candidates[0] if resp.candidates else None
    if cand is None:
        raise AIError("The AI returned no answer")
    reason = cand.finish_reason
    if reason == types.FinishReason.MAX_TOKENS:
        raise AIError("The AI answer was cut off (too long)")
    if reason not in (None, types.FinishReason.STOP, types.FinishReason.FINISH_REASON_UNSPECIFIED):
        raise AIError(f"The AI stopped early ({reason.value if reason else 'unknown'})")


class _QuotaExhausted(AIError):
    """The model's quota won't recover within the allowed wait (e.g. the daily free-tier cap)."""


def _models() -> list[str]:
    s = get_settings()
    models = [s.gemini_model]
    if s.gemini_fallback_model and s.gemini_fallback_model not in models:
        models.append(s.gemini_fallback_model)
    return models


def _quota_delay(e: genai_errors.APIError) -> float | None:
    # 429 = quota (Google says how long to wait); 503 = model overloaded (transient).
    if e.code == 429:
        return _retry_delay_seconds(e) or 20.0
    if e.code == 503:
        return 8.0
    return None


async def _generate_on(
    model: str, purpose: str, contents: Sequence[Content], config: types.GenerateContentConfig, max_quota_wait: float
):
    waited = 0.0
    while True:
        await _limiter.acquire()
        started = time.monotonic()
        resp = None
        try:
            resp = await _client().aio.models.generate_content(
                model=model, contents=cast(types.ContentListUnion, list(contents)), config=config
            )
            _check_finish(resp)
            _log_usage(purpose, started, resp, True, model)
            return resp
        except genai_errors.APIError as e:
            _log_usage(purpose, started, resp, False, model)
            delay = _quota_delay(e)
            if delay is not None and waited + delay <= max_quota_wait:
                log.info("ai purpose=%s model=%s busy; waiting %.0fs", purpose, model, delay)
                await asyncio.sleep(delay)
                waited += delay
                continue
            if e.code in (429, 503):
                raise _QuotaExhausted("The AI service is busy (rate limit reached). Please try again later.") from e
            raise AIError(f"AI service error ({e.code})") from e
        except AIError:
            _log_usage(purpose, started, resp, False, model)
            raise
        except Exception as e:  # network errors, timeouts
            _log_usage(purpose, started, resp, False, model)
            raise AIError(f"AI service unavailable ({type(e).__name__})") from e


async def _generate(
    purpose: str,
    contents: Sequence[Content],
    config: types.GenerateContentConfig,
    max_quota_wait: float = 70.0,
):
    """One model call with rate limiting and quota handling; falls back to GEMINI_FALLBACK_MODEL
    when the primary model's quota is exhausted."""
    last: AIError | None = None
    for model in _models():
        try:
            return await _generate_on(model, purpose, contents, config, max_quota_wait)
        except _QuotaExhausted as e:
            log.info("ai purpose=%s model=%s quota exhausted", purpose, model)
            last = e
    raise AIError("The AI service is busy (rate limit reached). Please try again later.") from last


async def generate_structured(
    *,
    purpose: str,
    system: str,
    contents: Sequence[Content],
    schema: type[T],
    thinking: str = "low",
    temperature: float | None = 0.0,
    max_output_tokens: int = 16384,
    seed: int | None = 7,
    max_quota_wait: float = 70.0,
) -> T:
    config = _config(
        system, thinking=thinking, temperature=temperature, max_output_tokens=max_output_tokens, schema=schema
    )
    if seed is not None:
        config.seed = seed
    attempt_contents = list(contents)
    last_error: Exception | None = None
    for attempt in range(2):
        resp = await _generate(purpose, attempt_contents, config, max_quota_wait)
        text = resp.text or ""
        try:
            return schema.model_validate_json(text)
        except (ValidationError, json.JSONDecodeError) as e:
            last_error = e
            log.warning("ai purpose=%s validation failed on attempt %d", purpose, attempt + 1)
            attempt_contents = [
                *contents,
                types.Content(role="model", parts=[types.Part.from_text(text=text)]),
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(
                            text=f"That JSON failed validation:\n{str(e)[:2000]}\nReturn corrected JSON only."
                        )
                    ],
                ),
            ]
    raise AIError("The AI returned data in an unexpected shape") from last_error


async def generate_text(
    *,
    purpose: str,
    system: str,
    contents: Sequence[Content],
    thinking: str = "low",
    temperature: float | None = 0.2,
    max_output_tokens: int = 8192,
    max_quota_wait: float = 30.0,
) -> str:
    resp = await _generate(
        purpose,
        contents,
        _config(system, thinking=thinking, temperature=temperature, max_output_tokens=max_output_tokens),
        max_quota_wait,
    )
    return resp.text or ""


async def stream_text(
    *,
    purpose: str,
    system: str,
    contents: Sequence[Content],
    thinking: str = "low",
    temperature: float | None = 0.2,
    max_output_tokens: int = 8192,
) -> AsyncIterator[str]:
    """Yield text chunks as they arrive (falls back to the next model only before any text is sent)."""
    config = _config(system, thinking=thinking, temperature=temperature, max_output_tokens=max_output_tokens)
    models = _models()
    for i, model in enumerate(models):
        await _limiter.acquire()
        started = time.monotonic()
        last = None
        sent = False
        try:
            stream = await _client().aio.models.generate_content_stream(
                model=model, contents=cast(types.ContentListUnion, list(contents)), config=config
            )
            async for chunk in stream:
                last = chunk
                if chunk.text:
                    sent = True
                    yield chunk.text
            if last is not None:
                _check_finish(last)
            _log_usage(purpose, started, last, True, model)
            return
        except genai_errors.APIError as e:
            _log_usage(purpose, started, last, False, model)
            if e.code in (429, 503) and not sent and i + 1 < len(models):
                log.info("ai purpose=%s model=%s busy; trying fallback", purpose, model)
                continue
            if e.code in (429, 503):
                raise AIError("The AI service is busy (rate limit reached). Please try again later.") from e
            raise AIError(f"AI service error ({e.code})") from e
        except AIError:
            _log_usage(purpose, started, last, False, model)
            raise
        except Exception as e:
            _log_usage(purpose, started, last, False, model)
            raise AIError(f"AI service unavailable ({type(e).__name__})") from e


async def generate_with_tools(
    *,
    purpose: str,
    system: str,
    contents: Sequence[Content],
    tools: list[types.Tool],
    thinking: str = "low",
    temperature: float | None = 0.0,
) -> types.GenerateContentResponse:
    """One model turn with function declarations; the caller runs the tool loop."""
    return await _generate(
        purpose,
        contents,
        _config(system, thinking=thinking, temperature=temperature, max_output_tokens=8192, tools=tools),
        max_quota_wait=30.0,
    )
