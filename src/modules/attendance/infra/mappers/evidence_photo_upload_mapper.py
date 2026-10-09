from infra.database.models.evidence_photo_upload import EvidencePhotoUploadModel
from modules.attendance.domain.entities.evidence_photo_upload import EvidencePhotoUpload


class EvidencePhotoUploadMapper:

    @staticmethod
    def to_domain(model: EvidencePhotoUploadModel) -> EvidencePhotoUpload:
        return EvidencePhotoUpload(
            id=model.id,
            session_id=model.session_id,
            file_key=model.file_key,
            url=model.url,
            status=model.status,
            uploaded_at=model.uploaded_at,
            confirmed_at=model.confirmed_at,
            attendance_record_id=model.attendance_record_id,
        )

    @staticmethod
    def to_model(entity: EvidencePhotoUpload) -> EvidencePhotoUploadModel:
        return EvidencePhotoUploadModel(
            id=entity.id,
            session_id=entity.session_id,
            file_key=entity.file_key,
            url=entity.url,
            status=entity.status,
            uploaded_at=entity.uploaded_at,
            confirmed_at=entity.confirmed_at,
            attendance_record_id=entity.attendance_record_id,
        )