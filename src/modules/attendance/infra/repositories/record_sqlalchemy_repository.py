import math
from typing import Any, cast
from uuid import UUID

from geoalchemy2.functions import ST_Distance, ST_GeographyFromText
from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.attendance_record import AttendanceRecordModel
from infra.database.models.room import RoomModel
from modules.attendance.domain.entities.attendance_record import AttendanceRecord
from modules.attendance.domain.repositories.attendance_record_repository import AttendanceRecordRepository
from modules.attendance.infra.mappers.attendance_record_mapper import AttendanceRecordMapper
from shared.enums.record_status import RecordStatus
from shared.exceptions import BusinessRuleException, ResourceAlreadyExistsException


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


class RecordSQLAlchemyRepository(AttendanceRecordRepository):

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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
        student_point = ST_GeographyFromText(f"SRID=4326;POINT({longitude} {latitude})")

        room_stmt = select(RoomModel.location).where(RoomModel.id == room_id)
        room_res = await self.session.execute(room_stmt)
        room_location = room_res.scalar_one_or_none()

        if room_location is not None:
            try:
                dist_stmt = select(ST_Distance(room_location, student_point))
                dist_res = await self.session.execute(dist_stmt)
                distance_meters = float(dist_res.scalar_one())
            except Exception:
                point = cast(Point, to_shape(cast(Any, room_location)))
                distance_meters = haversine_distance(latitude, longitude, point.y, point.x)
        else:
            distance_meters = 0.0

        within_radius = distance_meters <= tolerance_radius_meters

        flags = list(irregularity_flags or [])
        if not within_radius and "outside_radius" not in flags:
            flags.append("outside_radius")

        final_record_status = RecordStatus.IRREGULAR if flags else record_status

        record_entity = AttendanceRecord(
            session_id=session_id,
            tenant_member_id=tenant_member_id,
            latitude=latitude,
            longitude=longitude,
            distance_meters=distance_meters,
            within_radius=within_radius,
            gps_accuracy_meters=gps_accuracy_meters,
            record_status=final_record_status,
            irregularity_flags=flags,
            device_id=device_id,
            ip_address=ip_address,
            user_agent=user_agent,
            device_info=device_info,
        )

        model = AttendanceRecordMapper.to_model(record_entity)
        try:
            async with self.session.begin_nested():
                self.session.add(model)
                await self.session.flush()
            return AttendanceRecordMapper.to_domain(model)
        except IntegrityError:
            raise ResourceAlreadyExistsException("Presença já confirmada nesta sessão.")

    async def save(self, record: AttendanceRecord) -> AttendanceRecord:
        model = AttendanceRecordMapper.to_model(record)
        merged = await self.session.merge(model)
        await self.session.flush()
        return AttendanceRecordMapper.to_domain(merged)

    async def find_by_id(self, record_id: UUID) -> AttendanceRecord | None:
        stmt = select(AttendanceRecordModel).where(AttendanceRecordModel.id == record_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return AttendanceRecordMapper.to_domain(model) if model else None

    async def find_by_id_and_session(
        self, record_id: UUID, session_id: UUID
    ) -> AttendanceRecord | None:
        stmt = select(AttendanceRecordModel).where(
            AttendanceRecordModel.id == record_id,
            AttendanceRecordModel.session_id == session_id,
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return AttendanceRecordMapper.to_domain(model) if model else None

    async def find_by_session_and_member(
        self, session_id: UUID, tenant_member_id: UUID
    ) -> AttendanceRecord | None:
        stmt = select(AttendanceRecordModel).where(
            AttendanceRecordModel.session_id == session_id,
            AttendanceRecordModel.tenant_member_id == tenant_member_id,
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return AttendanceRecordMapper.to_domain(model) if model else None

    async def find_by_device_id_in_session(
        self, session_id: UUID, device_id: str
    ) -> AttendanceRecord | None:
        stmt = select(AttendanceRecordModel).where(
            AttendanceRecordModel.session_id == session_id,
            AttendanceRecordModel.device_id == device_id,
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return AttendanceRecordMapper.to_domain(model) if model else None

    async def list_by_session(
        self, session_id: UUID, record_status: RecordStatus | None = None
    ) -> list[AttendanceRecord]:
        stmt = select(AttendanceRecordModel).where(AttendanceRecordModel.session_id == session_id)
        if record_status is not None:
            stmt = stmt.where(AttendanceRecordModel.record_status == record_status)
        stmt = stmt.order_by(AttendanceRecordModel.confirmed_at.asc())
        result = await self.session.execute(stmt)
        return [AttendanceRecordMapper.to_domain(m) for m in result.scalars().all()]
