from collections.abc import AsyncIterator
from typing import Any, Protocol

from modules.assistant.domain.entities.llm_events import LLMStreamEvent


class LLMProvider(Protocol):
    """Contrato de streaming e tool calling para modelos de linguagem."""

    @property
    def model_name(self) -> str: ...

    def stream_turn(
        self,
        *,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AsyncIterator[LLMStreamEvent]: ...
