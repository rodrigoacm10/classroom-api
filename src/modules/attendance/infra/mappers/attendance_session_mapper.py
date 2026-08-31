from infra.database.models.attendance_session import AttendanceSessionModel
from modules.attendance.domain.entities.attendance_session import AttendanceSession, RoomInfo, SubjectClassInfo


class AttendanceSessionMapper:

    @staticmethod
    def to_domain(model: AttendanceSessionModel) -> AttendanceSession:
        subject_class_info = None
        sc = getattr(model, "subject_class", None)
        if sc is not None:
            subject_class_info = SubjectClassInfo(
                id=sc.id,
                name=sc.name,
                discipline_name=sc.discipline_name,
            )

        room_info = None
        r = getattr(model, "room", None)
        if r is not None:
            room_info = RoomInfo(
                id=r.id,
                name=r.name,
            )

        return AttendanceSession(
            id=model.id,
            subject_class_id=model.subject_class_id,
            room_id=model.room_id,
            subject_class=subject_class_info,
            room=room_info,
            day_code=model.day_code,
            opened_at=model.opened_at,
            expires_at=model.expires_at,
            closed_at=model.closed_at,
            status=model.status,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def to_model(entity: AttendanceSession) -> AttendanceSessionModel:
        return AttendanceSessionModel(
            id=entity.id,
            subject_class_id=entity.subject_class_id,
            room_id=entity.room_id,
            day_code=entity.day_code,
            opened_at=entity.opened_at,
            expires_at=entity.expires_at,
            closed_at=entity.closed_at,
            status=entity.status,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
