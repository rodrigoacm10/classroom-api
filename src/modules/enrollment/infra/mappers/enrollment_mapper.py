from infra.database.models.enrollment import EnrollmentModel
from modules.enrollment.domain.entities.enrollment import Enrollment


class EnrollmentMapper:

    @staticmethod
    def to_domain(model: EnrollmentModel) -> Enrollment:
        return Enrollment(
            id=model.id,
            subject_class_id=model.subject_class_id,
            tenant_member_id=model.tenant_member_id,
            status=model.status,
            deleted=model.deleted,
            enrolled_at=model.enrolled_at,
            dropped_at=model.dropped_at,
            deleted_at=model.deleted_at,
            drop_reason=model.drop_reason,
        )

    @staticmethod
    def to_model(entity: Enrollment) -> EnrollmentModel:
        return EnrollmentModel(
            id=entity.id,
            subject_class_id=entity.subject_class_id,
            tenant_member_id=entity.tenant_member_id,
            status=entity.status,
            deleted=entity.deleted,
            enrolled_at=entity.enrolled_at,
            dropped_at=entity.dropped_at,
            deleted_at=entity.deleted_at,
            drop_reason=entity.drop_reason,
        )
