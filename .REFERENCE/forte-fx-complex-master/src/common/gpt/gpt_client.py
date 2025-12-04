import openai
from typing import Optional, Dict, Any

from src.common.logger.logger_config import get_logger

logger = get_logger("gpt")


class GPTClient:
    def __init__(
        self,
        model: str,
        temperature: float,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_request_kwargs: Optional[Dict[str, Any]] = None,
    ):
        # Configure OpenAI
        openai.api_key = api_key or openai.api_key
        if base_url:
            openai.base_url = base_url

        self.client = openai
        self.model = model
        self.temperature = temperature
        self.request_defaults: Dict[str, Any] = dict(default_request_kwargs or {})

        logger.info("Initialized GPT client with params: model=%s, temperature=%s",
                    self.model, self.temperature)

    def send(self, system_prompt: str, user_prompt: str, **kwargs: Any):
        """
        Send with optional per-call overrides (model/temperature/etc.).
        """
        # Resolve effective params
        eff_model = kwargs.pop("model", self.model)
        eff_temp = kwargs.pop("temperature", self.temperature)

        # Merge any other request-level kwargs with defaults (per-call wins)
        req_kwargs = {**self.request_defaults, **kwargs}

        content = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        logger.info(
            "Sending LLM request | model=%s | temp=%s | sys='%s' | user='%s' | extras=%s",
            eff_model,
            eff_temp,
            _snip(system_prompt, 20),
            _snip(user_prompt, 20),
            list(req_kwargs.keys()),
        )

        if "model" in kwargs:
            logger.debug("kwargs.model type=%s, value=%r", type(kwargs["model"]).__name__, kwargs["model"])
        logger.debug("eff_model type=%s, value=%r", type(eff_model).__name__, eff_model)

        response = self.client.responses.create(
            model=eff_model,
            input=content,
            temperature=eff_temp,
            **req_kwargs,  # e.g., max_output_tokens=..., top_p=..., timeout=...
        )

        # Usage fields can be missing on some errors or providers
        usage = getattr(response, "usage", None)
        logger.info(
            "Model: %s | Input Tokens: %s | Output Tokens: %s",
            getattr(response, "model", "?"),
            getattr(usage, "input_tokens", "?") if usage else "?",
            getattr(usage, "output_tokens", "?") if usage else "?",
        )

        # Preferred: .output_text (OpenAI Responses API convenience)
        text = getattr(response, "output_text", None)
        if isinstance(text, str) and text.strip():
            return text

        return text


def _snip(text: Any, n: int = 20) -> str:
    if text is None:
        return ""
    s = str(text)
    s = " ".join(s.split())  # collapse whitespace/newlines
    return s[:n] + ("…" if len(s) > n else "")