import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, false, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from infra.database.base import Base
from shared.enums.enrollment_status import EnrollmentStatus


class EnrollmentModel(Base):
    __tablename__ = "subject_class_enrollments"
    __table_args__ = (
        Index(
            "uq_enrollment_active",
            "subject_class_id",
            "tenant_member_id",
            unique=True,
            postgresql_where=text("deleted = false"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    subject_class_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subject_classes.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant_members.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[EnrollmentStatus] = mapped_column(
        Enum(
            EnrollmentStatus,
            name="enrollment_status",
            create_type=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=EnrollmentStatus.ACTIVE,
        nullable=False,
    )
    deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
