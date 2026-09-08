from dataclasses import dataclass, field
from uuid import UUID

from shared.events.base_event import BaseEvent


@dataclass(frozen=True)
class AttendanceSessionOpenedEvent(BaseEvent):
    """
    Publicado quando um professor abre uma sessão de chamada.

    Consumidores registrados:
      - AttendancePushNotificationHandler.on_session_opened → Push para alunos matriculados
    """

    session_id: UUID = field(default=None)  # type: ignore[assignment]
    subject_class_id: UUID = field(default=None)  # type: ignore[assignment]
    subject_class_name: str = field(default="")
    day_code: str = field(default="")
    duration_minutes: int = field(default=0)


@dataclass(frozen=True)
class AttendanceSessionClosedEvent(BaseEvent):
    """
    Publicado quando a chamada é encerrada manualmente pelo professor ou admin.

    Consumidores registrados:
      - AttendancePushNotificationHandler.on_session_closed → Push para alunos matriculados
    """

    session_id: UUID = field(default=None)  # type: ignore[assignment]
    subject_class_id: UUID = field(default=None)  # type: ignore[assignment]
    subject_class_name: str = field(default="")
