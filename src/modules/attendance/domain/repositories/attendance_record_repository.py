from typing import Protocol
from uuid import UUID

from modules.attendance.domain.entities.attendance_record import AttendanceRecord
from shared.enums.record_status import RecordStatus


class AttendanceRecordRepository(Protocol):

    async def create_record(
        self,
        session_id: UUID,
        tenant_member_id: UUID,
        latitude: float,
        longitude: float,
        room_id: UUID,
        tolerance_radius_meters: float,
        gps_accuracy_meters: float | None = None,
        record_status: RecordStatus = RecordStatus.REGULAR,
        irregularity_flags: list[str] | None = None,
        device_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        device_info: dict | None = None,
    ) -> AttendanceRecord: ...

    async def save(self, record: AttendanceRecord) -> AttendanceRecord: ...

    async def find_by_id(self, record_id: UUID) -> AttendanceRecord | None: ...

    async def find_by_id_and_session(
        self, record_id: UUID, session_id: UUID
    ) -> AttendanceRecord | None: ...

    async def find_by_session_and_member(
        self, session_id: UUID, tenant_member_id: UUID
    ) -> AttendanceRecord | None: ...

    async def find_by_device_id_in_session(
        self, session_id: UUID, device_id: str
    ) -> AttendanceRecord | None: ...

    async def list_by_session(
        self, session_id: UUID, record_status: RecordStatus | None = None
    ) -> list[AttendanceRecord]: ...
