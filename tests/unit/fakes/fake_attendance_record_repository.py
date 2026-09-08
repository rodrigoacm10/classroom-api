import math
from uuid import UUID

from modules.attendance.domain.entities.attendance_record import AttendanceRecord
from modules.attendance.domain.repositories.attendance_record_repository import AttendanceRecordRepository
from shared.enums.record_status import RecordStatus
from shared.exceptions import BusinessRuleException


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


class FakeAttendanceRecordRepository(AttendanceRecordRepository):

    def __init__(self) -> None:
        self.records: dict[UUID, AttendanceRecord] = {}
        self.room_coordinates: dict[UUID, tuple[float, float]] = {}

    def seed_room_location(self, room_id: UUID, latitude: float, longitude: float) -> None:
        self.room_coordinates[room_id] = (latitude, longitude)

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
    ) -> AttendanceRecord:
        # Verificar duplicidade de sessão + membro
        for r in self.records.values():
            if r.session_id == session_id and r.tenant_member_id == tenant_member_id:
                raise BusinessRuleException("Presença já confirmada nesta sessão.")

        room_coords = self.room_coordinates.get(room_id, (latitude, longitude))
        distance_meters = haversine_distance(latitude, longitude, room_coords[0], room_coords[1])
        within_radius = distance_meters <= tolerance_radius_meters

        flags = list(irregularity_flags or [])
        if not within_radius and "outside_radius" not in flags:
            flags.append("outside_radius")

        final_status = RecordStatus.IRREGULAR if flags else RecordStatus.REGULAR

        record = AttendanceRecord(
            session_id=session_id,
            tenant_member_id=tenant_member_id,
            latitude=latitude,
            longitude=longitude,
            distance_meters=distance_meters,
            within_radius=within_radius,
            gps_accuracy_meters=gps_accuracy_meters,
            record_status=final_status,
            irregularity_flags=flags,
            device_id=device_id,
            ip_address=ip_address,
            user_agent=user_agent,
            device_info=device_info,
        )

        self.records[record.id] = record
        return record

    async def save(self, record: AttendanceRecord) -> AttendanceRecord:
        self.records[record.id] = record
        return record

    async def find_by_id(self, record_id: UUID) -> AttendanceRecord | None:
        return self.records.get(record_id)

    async def find_by_id_and_session(
        self, record_id: UUID, session_id: UUID
    ) -> AttendanceRecord | None:
        r = self.records.get(record_id)
        if r and r.session_id == session_id:
            return r
        return None

    async def find_by_session_and_member(
        self, session_id: UUID, tenant_member_id: UUID
    ) -> AttendanceRecord | None:
        for r in self.records.values():
            if r.session_id == session_id and r.tenant_member_id == tenant_member_id:
                return r
        return None

    async def find_by_device_id_in_session(
        self, session_id: UUID, device_id: str
    ) -> AttendanceRecord | None:
        for r in self.records.values():
            if r.session_id == session_id and r.device_id == device_id:
                return r
        return None

    async def list_by_session(
        self, session_id: UUID, record_status: RecordStatus | None = None
    ) -> list[AttendanceRecord]:
        results = [r for r in self.records.values() if r.session_id == session_id]
        if record_status is not None:
            results = [r for r in results if r.record_status == record_status]
        return results
