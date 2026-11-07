import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from geoalchemy2 import Geography
from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infra.database.base import Base
from shared.enums.session_status import SessionStatus

if TYPE_CHECKING:
    from infra.database.models.room import RoomModel
    from infra.database.models.subject_class import SubjectClassModel


class AttendanceSessionModel(Base):
    __tablename__ = "attendance_sessions"
    __table_args__ = (
        Index(
            "ix_attendance_sessions_open_active",
            "subject_class_id",
            text("opened_at DESC"),
            postgresql_where=text("status = 'open'"),
        ),
        Index(
            "ix_attendance_sessions_class_opened",
            "subject_class_id",
            "opened_at",
            postgresql_where=text("status != 'cancelled'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_class_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subject_classes.id", ondelete="CASCADE"), nullable=False
    )
    room_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True
    )
    custom_location: Mapped[str | None] = mapped_column(
        Geography(geometry_type="POINT", srid=4326), nullable=True
    )
    custom_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    custom_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    custom_tolerance_radius_meters: Mapped[int | None] = mapped_column(Integer, nullable=True)
    day_code: Mapped[str] = mapped_column(String(10), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[SessionStatus] = mapped_column(
        Enum(
            SessionStatus,
            name="session_status",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=SessionStatus.OPEN,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    subject_class: Mapped["SubjectClassModel"] = relationship("SubjectClassModel")
    room: Mapped["RoomModel | None"] = relationship("RoomModel")
