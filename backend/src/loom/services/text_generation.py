"""self-hosted/custom text generation over an OpenAI-compatible chat
completions endpoint.

sibling to transcription.py rather than a function added to it: the i/o
shape (prompts in, prose out), callers, and failure modes are different
enough that sharing one module would blur both. no vendor sdk is used —
plain httpx, matching the rest of the ai egress code.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from loom.services.ai_config import (
    assert_resolved_host_safe,
    read_capped_response,
    validate_endpoint,
)
from loom.services.text_generation_providers import get_text_gen_provider

logger = logging.getLogger(__name__)

# a chat completion is a single small-ish request/response; no reason to
# allow anywhere near transcription's multi-minute ceiling.
_TIMEOUT = httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0)
# generated prose is bounded by max_tokens; a response far larger than
# that from a self-hosted/custom endpoint is either misbehaving or
# hostile, not a legitimate long completion.
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class TextGenerationError(Exception):
    """raised when the endpoint returns an unusable response."""


@dataclass(frozen=True)
class TextGenerationResult:
    text: str
    model: str
    provenance: dict[str, Any]


def _provenance(provider: str, model: str, base_url: str) -> dict[str, Any]:
    return {
        "provider": provider or "custom",
        "endpoint": httpx.URL(base_url).host,
        "model": model,
    }


async def generate_text(
    *,
    provider: str = "",
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 1024,
    temperature: float = 0.2,
) -> TextGenerationResult:
    """generate text via a self-hosted/custom chat completions endpoint.

    re-validates the endpoint immediately before dispatch — mirroring
    :func:`transcription.transcribe_via_cloud` — rather than trusting it
    was checked when saved, and resolves the hostname to catch a
    dns-rebinding attempt a static url check alone can't see.
    """
    known = get_text_gen_provider(provider) if provider else None
    allow_local = known.base_url_editable if known else True
    validate_endpoint(base_url, allow_local=allow_local)
    assert_resolved_host_safe(base_url, allow_local=allow_local)

    endpoint = base_url.rstrip("/") + "/chat/completions"
    request_body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    async with (
        httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client,
        client.stream(
            "POST", endpoint, json=request_body, headers=headers
        ) as resp,
    ):
        resp.raise_for_status()
        raw = await read_capped_response(resp, _MAX_RESPONSE_BYTES)
    body = json.loads(raw)

    choices = body.get("choices") or []
    if not choices:
        raise TextGenerationError("ai endpoint returned no completion choices")
    message = choices[0].get("message") or {}
    text = str(message.get("content") or "").strip()
    if not text:
        raise TextGenerationError("ai endpoint returned an empty completion")

    return TextGenerationResult(
        text=text,
        model=model,
        provenance=_provenance(provider, model, base_url),
    )
