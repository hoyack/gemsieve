"""Anthropic AI provider — Claude API client."""

from __future__ import annotations

import json


class AnthropicProvider:
    """Anthropic API client for Claude models."""

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def complete(
        self,
        prompt: str,
        model: str,
        system: str = "",
        response_format: str | None = None,
    ) -> dict:
        """Send a prompt to Claude and return parsed response."""
        client = self._get_client()

        messages = [{"role": "user", "content": prompt}]

        kwargs: dict = {
            "model": model,
            "max_tokens": 4096,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        response = client.messages.create(**kwargs)

        response_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                response_text += block.text

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
                try:
                    json_start = response_text.index("```") + 3
                    json_end = response_text.index("```", json_start)
                    return json.loads(response_text[json_start:json_end].strip())
                except (ValueError, json.JSONDecodeError):
                    pass
            return {"text": response_text}
