from infra.database.models.subject_class import SubjectClassModel
from modules.subject_class.domain.entities.subject_class import SubjectClass


class SubjectClassMapper:

    @staticmethod
    def to_domain(model: SubjectClassModel) -> SubjectClass:
        return SubjectClass(
            id=model.id,
            tenant_id=model.tenant_id,
            professor_id=model.professor_id,
            room_id=model.room_id,
            name=model.name,
            discipline_name=model.discipline_name,
            deleted=model.deleted,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def to_model(entity: SubjectClass) -> SubjectClassModel:
        return SubjectClassModel(
            id=entity.id,
            tenant_id=entity.tenant_id,
            professor_id=entity.professor_id,
            room_id=entity.room_id,
            name=entity.name,
            discipline_name=entity.discipline_name,
            deleted=entity.deleted,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
