"""Anthropic Claude client wrapper — direct API, conversational."""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List

from anthropic import Anthropic, APIError
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings


class ClaudeClient:
    def __init__(self, api_key: str, model: str, max_tokens: int, temperature: float) -> None:
        self.client = Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    @retry(
        reraise=True,
        retry=retry_if_exception_type(APIError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
    )
    def complete(
        self,
        system: str,
        messages: List[Dict[str, str]],
        max_tokens: int | None = None,
        temperature: float | None = None,
        model: str | None = None,
    ) -> Dict[str, Any]:
        """Non-streaming completion. `messages` = list of {role, content} in Anthropic format."""
        used_model = model or self.model
        resp = self.client.messages.create(
            model=used_model,
            system=system,
            messages=messages,
            max_tokens=max_tokens or self.max_tokens,
            temperature=self.temperature if temperature is None else temperature,
        )
        text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
        usage = {
            "input_tokens": getattr(resp.usage, "input_tokens", 0),
            "output_tokens": getattr(resp.usage, "output_tokens", 0),
        }
        logger.debug(f"Claude usage: {usage}")
        return {"text": text, "usage": usage, "model": used_model, "stop_reason": resp.stop_reason}


@lru_cache(maxsize=1)
def get_claude_client() -> ClaudeClient:
    s = get_settings()
    return ClaudeClient(
        api_key=s.anthropic_api_key,
        model=s.claude_model,
        max_tokens=s.claude_max_tokens,
        temperature=s.claude_temperature,
    )
