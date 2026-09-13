from uuid import UUID

from pydantic import BaseModel, ConfigDict


class StudentReportResponse(BaseModel):
    tenant_member_id: UUID
    student_name: str
    total_present: int
    total_absent: int
    total_irregular: int
    frequency_rate: float
    at_risk: bool
    avg_distance_meters: float
    confirmations_near_limit: int

    model_config = ConfigDict(from_attributes=True)


class ClassReportResponse(BaseModel):
    subject_class_id: UUID
    total_students: int
    class_average_frequency: float
    students_at_risk: int
    students: list[StudentReportResponse]
    strategy_used: str
    workers_used: int
    duration_ms: float

    model_config = ConfigDict(from_attributes=True)
