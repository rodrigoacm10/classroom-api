import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from google import genai
from google.genai import errors, types

from modules.assistant.domain.entities.llm_events import LLMStreamEvent, ToolCallRequest

logger = logging.getLogger(__name__)

DEFAULT_CHAT_MODEL = "gemini-3.5-flash-lite"
FALLBACK_CHAT_MODELS: tuple[str, ...] = (
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
)
RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})
MAX_ATTEMPTS_PER_MODEL = 3
BASE_RETRY_DELAY_SECONDS = 0.8


class GeminiLLMProvider:
    """Adapter de streaming e tool calling usando o SDK oficial google-genai."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = DEFAULT_CHAT_MODEL,
        temperature: float = 0.2,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError(
                "GEMINI_API_KEY não configurada. Defina a variável no .env para usar o assistente."
            )
        self._client = genai.Client(api_key=api_key.strip())
        self._model = model
        self._temperature = temperature

    @property
    def model_name(self) -> str:
        return self._model

    async def stream_turn(
        self,
        *,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AsyncIterator[LLMStreamEvent]:
        contents = self._build_contents(messages)
        gemini_tools = self._build_tools(tools)

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=self._temperature,
            tools=gemini_tools if gemini_tools else None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        candidate_models: list[str] = [self._model]
        for fallback in FALLBACK_CHAT_MODELS:
            if fallback not in candidate_models:
                candidate_models.append(fallback)

        tokens_in: int | None = None
        tokens_out: int | None = None
        last_exc: Exception | None = None

        for model_idx, candidate_model in enumerate(candidate_models):
            for attempt in range(1, MAX_ATTEMPTS_PER_MODEL + 1):
                emitted_in_attempt = False
                try:
                    stream = await self._client.aio.models.generate_content_stream(
                        model=candidate_model,
                        contents=contents,
                        config=config,
                    )
                    self._model = candidate_model

                    async for chunk in stream:
                        if chunk.usage_metadata is not None:
                            if chunk.usage_metadata.prompt_token_count is not None:
                                tokens_in = int(chunk.usage_metadata.prompt_token_count)
                            if chunk.usage_metadata.candidates_token_count is not None:
                                tokens_out = int(chunk.usage_metadata.candidates_token_count)

                        for candidate in chunk.candidates or []:
                            content = candidate.content
                            if content is None or not content.parts:
                                continue
                            for part in content.parts:
                                if part.function_call is not None and part.function_call.name:
                                    args = (
                                        dict(part.function_call.args)
                                        if part.function_call.args is not None
                                        else {}
                                    )
                                    emitted_in_attempt = True
                                    yield LLMStreamEvent(
                                        kind="tool_call",
                                        tool_call=ToolCallRequest(
                                            name=part.function_call.name,
                                            arguments=args,
                                            provider_part=part,
                                        ),
                                    )
                                elif part.text and not getattr(part, "thought", False):
                                    emitted_in_attempt = True
                                    yield LLMStreamEvent(kind="delta", text=part.text)

                    if tokens_in is not None or tokens_out is not None:
                        yield LLMStreamEvent(
                            kind="usage",
                            tokens_in=tokens_in,
                            tokens_out=tokens_out,
                        )
                    return

                except (errors.ServerError, errors.ClientError) as exc:
                    last_exc = exc
                    status_code = getattr(exc, "code", None)
                    is_retryable = (
                        isinstance(exc, errors.ServerError) or status_code in RETRYABLE_STATUS_CODES
                    )

                    # Se o stream caiu no meio depois de já ter emitido texto parcial,
                    # propaga para que o SendMessageUseCase preserve a resposta parcial.
                    if emitted_in_attempt:
                        raise

                    if is_retryable and attempt < MAX_ATTEMPTS_PER_MODEL:
                        delay = BASE_RETRY_DELAY_SECONDS * attempt
                        logger.warning(
                            "Gemini '%s' retornou %s (tentativa %d/%d); aguardando %.1fs...",
                            candidate_model,
                            status_code or type(exc).__name__,
                            attempt,
                            MAX_ATTEMPTS_PER_MODEL,
                            delay,
                        )
                        await asyncio.sleep(delay)
                        continue

                    if model_idx < len(candidate_models) - 1:
                        logger.warning(
                            "Modelo Gemini '%s' indisponível (%s); tentando fallback '%s'.",
                            candidate_model,
                            exc,
                            candidate_models[model_idx + 1],
                        )
                        break

                    raise

        if last_exc is not None:
            raise last_exc

    @staticmethod
    def _build_tools(tools: list[dict[str, Any]]) -> list[types.Tool]:
        if not tools:
            return []
        declarations = [
            types.FunctionDeclaration(
                name=tool["name"],
                description=tool.get("description", ""),
                parameters_json_schema=tool.get("parameters"),
            )
            for tool in tools
        ]
        return [types.Tool(function_declarations=declarations)]

    @staticmethod
    def _build_contents(messages: list[dict[str, Any]]) -> list[types.Content]:
        contents: list[types.Content] = []
        for msg in messages:
            role = msg.get("role")
            if role == "user":
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=str(msg.get("content", "")))],
                    )
                )
            elif role == "assistant":
                tool_calls = msg.get("tool_calls")
                parts: list[types.Part] = []
                if msg.get("content"):
                    parts.append(types.Part.from_text(text=str(msg["content"])))
                if isinstance(tool_calls, list):
                    for tc in tool_calls:
                        raw_part = tc.get("provider_part")
                        if isinstance(raw_part, types.Part):
                            parts.append(raw_part)
                        else:
                            parts.append(
                                types.Part.from_function_call(
                                    name=str(tc["name"]),
                                    args=dict(tc.get("arguments") or {}),
                                )
                            )
                if parts:
                    contents.append(types.Content(role="model", parts=parts))
            elif role == "tool":
                contents.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_function_response(
                                name=str(msg["name"]),
                                response={"result": str(msg.get("content", ""))},
                            )
                        ],
                    )
                )
        return contents
