"""OpenAI LLM provider implementation."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Union

from market_agent.analysis.stock.interfaces import AnalysisProvider
from market_agent.analysis.stock.prompt import SYSTEM_PROMPT, build_user_prompt
from market_agent.analysis.stock.schema import normalize_section_result

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-5-mini"
DEFAULT_TIMEOUT_SEC = 30


@dataclass(slots=True)
class OpenAIProvider(AnalysisProvider):
    api_key: str
    model: str = DEFAULT_MODEL
    temperature: float = 0.2
    timeout_sec: int = DEFAULT_TIMEOUT_SEC
    name: str = "openai"

    def analyze_section(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        response_text = _openai_chat(
            api_key=self.api_key,
            model=self.model,
            temperature=self.temperature,
            timeout_sec=self.timeout_sec,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(payload)},
            ],
        )
        return normalize_section_result(_safe_json(response_text)).as_dict()


def resolve_openai_provider(
    *,
    api_key: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.2,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> OpenAIProvider:
    resolved_key = api_key or os.getenv("OPENAI_API_KEY")
    if not resolved_key:
        raise RuntimeError("OpenAI API key is required. Set OPENAI_API_KEY.")
    return OpenAIProvider(
        api_key=resolved_key,
        model=model,
        temperature=temperature,
        timeout_sec=timeout_sec,
    )


def _safe_json(text: str) -> Union[Dict[str, Any], str]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _openai_chat(
    *,
    api_key: str,
    model: str,
    temperature: float,
    timeout_sec: int,
    messages: Iterable[Dict[str, str]],
) -> str:
    body = json.dumps(
        {
            "model": model,
            "temperature": temperature,
            "messages": list(messages),
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        OPENAI_API_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI API error: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI API connection error: {exc}") from exc

    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError("OpenAI API returned no choices.")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not content:
        raise RuntimeError("OpenAI API returned empty content.")
    return content


__all__ = [
    "OpenAIProvider",
    "resolve_openai_provider",
    "DEFAULT_MODEL",
    "DEFAULT_TIMEOUT_SEC",
]
