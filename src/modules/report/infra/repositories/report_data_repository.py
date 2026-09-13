from typing import Any, cast
from uuid import UUID

from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database.models.attendance_record import AttendanceRecordModel
from infra.database.models.attendance_session import AttendanceSessionModel
from infra.database.models.enrollment import EnrollmentModel
from infra.database.models.room import RoomModel
from infra.database.models.subject_class import SubjectClassModel
from infra.database.models.tenant import TenantMemberModel
from infra.database.models.user import UserModel
from modules.report.domain.entities.student_attendance_data import (
    RawConfirmation,
    StudentAttendanceData,
)


class ReportDataRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def load_class_data(
        self, tenant_id: UUID, subject_class_id: UUID
    ) -> list[StudentAttendanceData]:
        """
        Uma única ida ao banco. Monta a estrutura completa em memória.
        A partir daqui, NENHUMA outra query é feita — o cálculo (Fase 2) opera
        inteiramente sobre os dados já carregados.
        """
        total_sessions_stmt = select(AttendanceSessionModel.id).where(
            AttendanceSessionModel.subject_class_id == subject_class_id
        )
        session_ids = (await self.session.execute(total_sessions_stmt)).scalars().all()
        total_sessions = len(session_ids)

        enrollments_stmt = (
            select(EnrollmentModel, TenantMemberModel, UserModel)
            .join(TenantMemberModel, TenantMemberModel.id == EnrollmentModel.tenant_member_id)
            .join(UserModel, UserModel.id == TenantMemberModel.user_id)
            .where(
                EnrollmentModel.subject_class_id == subject_class_id,
                EnrollmentModel.deleted.is_(False),
            )
        )
        enrollment_rows = (await self.session.execute(enrollments_stmt)).all()

        records_by_member: dict[UUID, list[AttendanceRecordModel]] = {}
        if session_ids:
            records_stmt = select(AttendanceRecordModel).where(
                AttendanceRecordModel.session_id.in_(session_ids)
            )
            all_records = (await self.session.execute(records_stmt)).scalars().all()
            for record in all_records:
                records_by_member.setdefault(record.tenant_member_id, []).append(record)

        room = await self._get_class_room(subject_class_id)
        room_lat = self._extract_lat(room.location) if room is not None else 0.0
        room_lon = self._extract_lon(room.location) if room is not None else 0.0
        tolerance = float(room.tolerance_radius_meters) if room is not None else 50.0

        result: list[StudentAttendanceData] = []
        for enrollment, member, user in enrollment_rows:
            member_records = records_by_member.get(member.id, [])
            confirmations = [
                RawConfirmation(
                    latitude=self._extract_lat(r.student_location),
                    longitude=self._extract_lon(r.student_location),
                    record_status=self._status_value(r.record_status),
                )
                for r in member_records
            ]
            result.append(
                StudentAttendanceData(
                    tenant_member_id=member.id,
                    student_name=user.name,
                    total_sessions=total_sessions,
                    confirmations=confirmations,
                    room_lat=room_lat,
                    room_lon=room_lon,
                    tolerance_radius_meters=tolerance,
                )
            )
        return result

    async def _get_class_room(self, subject_class_id: UUID) -> RoomModel | None:
        stmt = (
            select(RoomModel)
            .join(SubjectClassModel, SubjectClassModel.room_id == RoomModel.id)
            .where(SubjectClassModel.id == subject_class_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    def _extract_lat(location: Any) -> float:
        if location is None:
            return 0.0
        point = cast(Point, to_shape(cast(Any, location)))
        return float(point.y)

    @staticmethod
    def _extract_lon(location: Any) -> float:
        if location is None:
            return 0.0
        point = cast(Point, to_shape(cast(Any, location)))
        return float(point.x)

    @staticmethod
    def _status_value(record_status: Any) -> str:
        value = getattr(record_status, "value", record_status)
        return str(value)
