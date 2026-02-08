"""AI provider protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class AIProvider(Protocol):
    """Protocol for AI model providers."""

    def complete(
        self,
        prompt: str,
        model: str,
        system: str = "",
        response_format: str | None = None,
    ) -> dict:
        """Send a prompt and get a structured response.

        Args:
            prompt: the user prompt
            model: model name/identifier
            system: optional system prompt
            response_format: if "json", request JSON output

        Returns:
            Parsed dict from JSON response, or {"text": raw_text} if not JSON.
        """
        ...
