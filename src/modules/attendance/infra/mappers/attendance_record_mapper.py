from typing import Any, cast

from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import to_shape
from shapely.geometry import Point

from infra.database.models.attendance_record import AttendanceRecordModel
from modules.attendance.domain.entities.attendance_record import AttendanceRecord


class AttendanceRecordMapper:

    @staticmethod
    def to_domain(model: AttendanceRecordModel) -> AttendanceRecord:
        point = cast(Point, to_shape(cast(Any, model.student_location)))
        return AttendanceRecord(
            id=model.id,
            session_id=model.session_id,
            tenant_member_id=model.tenant_member_id,
            confirmed_at=model.confirmed_at,
            latitude=point.y,
            longitude=point.x,
            distance_meters=model.distance_meters,
            within_radius=model.within_radius,
            gps_accuracy_meters=model.gps_accuracy_meters,
            record_status=model.record_status,
            irregularity_flags=model.irregularity_flags or [],
            reviewed_by=model.reviewed_by,
            reviewed_at=model.reviewed_at,
            review_note=model.review_note,
            device_id=model.device_id,
            ip_address=str(model.ip_address) if model.ip_address is not None else None,
            user_agent=model.user_agent,
            device_info=model.device_info,
            evidence_photo_url=model.evidence_photo_url,
        )

    @staticmethod
    def to_model(entity: AttendanceRecord) -> AttendanceRecordModel:
        wkt = WKTElement(f"POINT({entity.longitude} {entity.latitude})", srid=4326)
        return AttendanceRecordModel(
            id=entity.id,
            session_id=entity.session_id,
            tenant_member_id=entity.tenant_member_id,
            confirmed_at=entity.confirmed_at,
            student_location=wkt,
            distance_meters=entity.distance_meters,
            within_radius=entity.within_radius,
            gps_accuracy_meters=entity.gps_accuracy_meters,
            record_status=entity.record_status,
            irregularity_flags=entity.irregularity_flags,
            reviewed_by=entity.reviewed_by,
            reviewed_at=entity.reviewed_at,
            review_note=entity.review_note,
            device_id=entity.device_id,
            ip_address=entity.ip_address,
            user_agent=entity.user_agent,
            device_info=entity.device_info,
            evidence_photo_url=entity.evidence_photo_url,
        )
