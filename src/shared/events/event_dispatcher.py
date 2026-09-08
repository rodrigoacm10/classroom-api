import logging
from collections import defaultdict
from typing import Awaitable, Callable, Type

from shared.events.base_event import BaseEvent

logger = logging.getLogger(__name__)

EventHandler = Callable[[BaseEvent], Awaitable[None]]


class EventDispatcher:
    """
    Barramento de eventos in-memory da aplicação.

    Os Use Cases publicam eventos descrevendo o que aconteceu no negócio.
    Os Handlers (na camada de aplicação/infra) reagem a esses eventos de forma desacoplada.

    Características:
    - Fire-and-continue: se um handler falhar, os demais handlers do mesmo evento continuam executando.
    - O Use Case não sabe quem está ouvindo nem se algum handler falhou.
    - As falhas dos handlers são logadas mas nunca propagadas de volta ao Use Case.
    """

    def __init__(self) -> None:
        self._handlers: dict[Type[BaseEvent], list[EventHandler]] = defaultdict(list)

    def register(self, event_type: Type[BaseEvent], handler: Callable[..., Awaitable[None]]) -> None:
        """Registra um handler para um tipo de evento."""
        self._handlers[event_type].append(handler)  # type: ignore[arg-type]

    async def publish(self, event: BaseEvent) -> None:
        """
        Publica um evento para todos os handlers registrados para aquele tipo.
        Falhas em handlers individuais são isoladas e logadas.
        """
        handlers = self._handlers.get(type(event), [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "Event handler '%s' failed for event '%s' (event_id=%s)",
                    getattr(handler, "__name__", repr(handler)),
                    type(event).__name__,
                    event.event_id,
                )
