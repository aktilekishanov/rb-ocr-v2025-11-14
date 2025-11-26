from __future__ import annotations

import json
from typing import Any

import httpx


class CompletionsHttpClient:
    def __init__(
        self,
        base_url: str | None,
        timeout_seconds: int,
        verify_ssl: bool = True,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._verify_ssl = verify_ssl
        self._transport = transport

    def _client(self) -> httpx.Client:
        if not self._base_url:
            raise RuntimeError("LLM base_url is not configured")
        return httpx.Client(
            base_url=self._base_url,
            timeout=self._timeout_seconds,
            verify=self._verify_ssl,
            transport=self._transport,
        )

    def complete(self, content: str, *, model: str, temperature: float, max_tokens: int) -> dict[str, Any]:
        payload = {
            "Model": model,
            "Content": content,
            "Temperature": temperature,
            "MaxTokens": max_tokens,
        }
        with self._client() as client:
            resp = client.post("", json=payload)
            resp.raise_for_status()
            try:
                data = resp.json()
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
            text = resp.text or ""
            last_obj: dict[str, Any] | None = None
            for line in reversed(text.splitlines()):
                s = line.strip()
                if not s:
                    continue
                try:
                    obj = json.loads(s)
                    if isinstance(obj, dict):
                        last_obj = obj
                        break
                except Exception:
                    continue
            if last_obj is None:
                raise RuntimeError("LLM completion response not JSON")
            return last_obj

    def extract_message_content(self, data: dict[str, Any]) -> str:
        try:
            choices = data.get("choices")
            if isinstance(choices, list) and choices:
                msg = choices[0].get("message", {})
                content = msg.get("content")
                if isinstance(content, str) and content.strip():
                    return content
        except Exception:
            pass
        content = data.get("Content")
        if isinstance(content, str) and content.strip():
            return content
        return json.dumps(data)
