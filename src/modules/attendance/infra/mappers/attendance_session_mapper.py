from geoalchemy2.elements import WKTElement

from infra.database.models.attendance_session import AttendanceSessionModel
from modules.attendance.domain.entities.attendance_session import (
    AttendanceSession,
    RoomInfo,
    SubjectClassInfo,
)


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
            custom_latitude=getattr(model, "custom_latitude", None),
            custom_longitude=getattr(model, "custom_longitude", None),
            custom_tolerance_radius_meters=getattr(model, "custom_tolerance_radius_meters", None),
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
        custom_loc = None
        if entity.custom_longitude is not None and entity.custom_latitude is not None:
            custom_loc = WKTElement(
                f"POINT({entity.custom_longitude} {entity.custom_latitude})", srid=4326
            )

        return AttendanceSessionModel(
            id=entity.id,
            subject_class_id=entity.subject_class_id,
            room_id=entity.room_id,
            custom_location=custom_loc,
            custom_latitude=entity.custom_latitude,
            custom_longitude=entity.custom_longitude,
            custom_tolerance_radius_meters=entity.custom_tolerance_radius_meters,
            day_code=entity.day_code,
            opened_at=entity.opened_at,
            expires_at=entity.expires_at,
            closed_at=entity.closed_at,
            status=entity.status,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
