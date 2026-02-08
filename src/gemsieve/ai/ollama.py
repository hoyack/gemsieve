"""Ollama AI provider — HTTP client for local LLM inference."""

from __future__ import annotations

import json
import time

import httpx


class OllamaProvider:
    """Ollama HTTP API client for local or cloud inference."""

    def __init__(self, base_url: str = "http://localhost:11434", api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def complete(
        self,
        prompt: str,
        model: str,
        system: str = "",
        response_format: str | None = None,
    ) -> dict:
        """Send a prompt to Ollama and return parsed response."""
        payload: dict = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }

        if system:
            payload["system"] = system

        if response_format == "json":
            payload["format"] = "json"

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        max_retries = 3
        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=120.0) as client:
                    resp = client.post(
                        f"{self.base_url}/api/generate",
                        json=payload,
                        headers=headers,
                    )
                    resp.raise_for_status()

                data = resp.json()
                response_text = data.get("response", "")

                # Try to parse as JSON
                try:
                    return json.loads(response_text)
                except json.JSONDecodeError:
                    # Try to extract JSON from markdown code blocks
                    if "```json" in response_text:
                        json_start = response_text.index("```json") + 7
                        json_end = response_text.index("```", json_start)
                        return json.loads(response_text[json_start:json_end].strip())
                    elif "```" in response_text:
                        json_start = response_text.index("```") + 3
                        json_end = response_text.index("```", json_start)
                        return json.loads(response_text[json_start:json_end].strip())
                    return {"text": response_text}

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise ConnectionError(
                    f"Failed to connect to Ollama at {self.base_url}: {e}"
                ) from e
