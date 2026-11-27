from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class ToolCallRequest:
    """Pedido de execução de ferramenta emitido pelo LLM."""

    name: str
    arguments: dict[str, Any]
    provider_part: Any | None = None


@dataclass(frozen=True)
class LLMStreamEvent:
    """Evento unitário emitido durante o streaming de um turno do LLM."""

    kind: Literal["delta", "tool_call", "usage"]
    text: str = ""
    tool_call: ToolCallRequest | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
