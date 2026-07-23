import json
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlparse

import httpx

from ..config import get_settings


class ModelUnavailable(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.settings = get_settings()
        self.base_url = (base_url or self.settings.ollama_url).rstrip("/")
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Invalid Ollama URL")

    async def health(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                data = response.json()
            return {"available": True, "models": data.get("models", [])}
        except (httpx.HTTPError, ValueError) as exc:
            return {"available": False, "models": [], "error": str(exc)}

    async def list_models(self) -> list[dict[str, Any]]:
        state = await self.health()
        return state.get("models", [])

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        context_length: int | None = None,
    ) -> str:
        payload = {
            "model": model or self.settings.ollama_model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature if temperature is not None else self.settings.model_temperature,
                "num_predict": max_tokens or self.settings.model_max_tokens,
                "num_ctx": context_length or self.settings.model_context_length,
            },
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
                response = await client.post(f"{self.base_url}/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()
            return str(data.get("message", {}).get("content", "")).strip()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise ModelUnavailable(f"Ollama rejected the request: {detail}") from exc
        except httpx.HTTPError as exc:
            raise ModelUnavailable("Local model service is not reachable") from exc

    async def pull(self, model: str) -> AsyncIterator[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST", f"{self.base_url}/api/pull", json={"name": model, "stream": True}
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line:
                        yield json.loads(line)

    async def delete(self, model: str) -> None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request("DELETE", f"{self.base_url}/api/delete", json={"name": model})
            response.raise_for_status()


ollama = OllamaClient()
