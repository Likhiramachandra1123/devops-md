"""Anthropic Claude client wrapper — direct API, conversational."""
from __future__ import annotations

import warnings
from functools import lru_cache
from typing import Any, Dict, List

from anthropic import Anthropic, APIError, BadRequestError
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings

# Silence the SDK-level DeprecationWarning some newer Claude models emit for
# `temperature`/`top_p`/`top_k`. We already handle the actual API rejection
# below; the warning itself is noise in the logs.
warnings.filterwarnings(
    "ignore",
    message=r".*(temperature|top_p|top_k).*deprecated.*",
    category=DeprecationWarning,
)
warnings.filterwarnings(
    "ignore",
    message=r".*(temperature|top_p|top_k).*deprecated.*",
    category=UserWarning,
)

# Substrings we look for in the API error message to detect that the model
# rejected the sampling params (e.g. Claude 4 with extended thinking, or
# newer models where `temperature` is no longer accepted).
_UNSUPPORTED_SAMPLING_HINTS = (
    "temperature",
    "top_p",
    "top_k",
    "deprecated",
    "sampling",
    "extended thinking",
)


class ClaudeClient:
    def __init__(self, api_key: str, model: str, max_tokens: int, temperature: float) -> None:
        self.client = Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        # Models observed to reject sampling params. Populated at runtime so we
        # skip those params on subsequent calls to the same model.
        self._no_sampling_models: set[str] = set()

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
        effective_temp = self.temperature if temperature is None else temperature

        kwargs: Dict[str, Any] = {
            "model": used_model,
            "system": system,
            "messages": messages,
            "max_tokens": max_tokens or self.max_tokens,
        }
        if used_model not in self._no_sampling_models:
            kwargs["temperature"] = effective_temp

        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                resp = self.client.messages.create(**kwargs)
            for w in caught:
                wmsg = str(w.message).lower()
                if "deprecated" in wmsg and any(
                    p in wmsg for p in ("temperature", "top_p", "top_k")
                ):
                    if used_model not in self._no_sampling_models:
                        logger.warning(
                            f"Model {used_model} emitted deprecation warning for sampling "
                            f"params ({w.message}); dropping them on future calls."
                        )
                        self._no_sampling_models.add(used_model)
        except BadRequestError as e:
            msg = str(e).lower()
            if any(hint in msg for hint in _UNSUPPORTED_SAMPLING_HINTS) and (
                "temperature" in kwargs or "top_p" in kwargs or "top_k" in kwargs
            ):
                logger.warning(
                    f"Model {used_model} rejected sampling params ({e}); "
                    f"retrying without them and caching for future calls."
                )
                self._no_sampling_models.add(used_model)
                kwargs.pop("temperature", None)
                kwargs.pop("top_p", None)
                kwargs.pop("top_k", None)
                resp = self.client.messages.create(**kwargs)
            else:
                raise

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
