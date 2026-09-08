import uuid
from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from infra.database.base import Base
from shared.enums.record_status import RecordStatus


class AttendanceRecordModel(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "tenant_member_id",
            name="uq_attendance_record_session_member",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("attendance_sessions.id", ondelete="CASCADE"), nullable=False
    )
    tenant_member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant_members.id", ondelete="CASCADE"), nullable=False
    )
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Geolocalização
    student_location: Mapped[str] = mapped_column(
        Geography(geometry_type="POINT", srid=4326), nullable=False
    )
    distance_meters: Mapped[float] = mapped_column(Float, nullable=False)
    within_radius: Mapped[bool] = mapped_column(Boolean, nullable=False)
    gps_accuracy_meters: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Auditoria de Irregularidades
    record_status: Mapped[RecordStatus] = mapped_column(
        Enum(RecordStatus, name="record_status", native_enum=True),
        default=RecordStatus.REGULAR,
        nullable=False,
    )
    irregularity_flags: Mapped[list[str]] = mapped_column(
        ARRAY(String), server_default="{}", nullable=False
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant_members.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Device Fingerprint
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_info: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    evidence_photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
