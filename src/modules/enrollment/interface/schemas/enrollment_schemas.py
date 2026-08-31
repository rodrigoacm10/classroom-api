from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.enums.enrollment_status import EnrollmentStatus


class EnrollStudentRequest(BaseModel):
    tenant_member_id: UUID


class EnrollmentResponse(BaseModel):
    id: UUID
    subject_class_id: UUID
    tenant_member_id: UUID
    status: EnrollmentStatus
    enrolled_at: datetime

    model_config = ConfigDict(from_attributes=True)
