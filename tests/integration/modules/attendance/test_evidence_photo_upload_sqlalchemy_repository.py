from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from modules.attendance.application.use_cases.cleanup_expired_evidence_uploads import (
    CleanupExpiredEvidenceUploadsInput,
    CleanupExpiredEvidenceUploadsUseCase,
)
from modules.attendance.domain.entities.attendance_session import AttendanceSession
from modules.attendance.domain.entities.evidence_photo_upload import EvidencePhotoUpload
from modules.attendance.infra.repositories.evidence_photo_upload_sqlalchemy_repository import (
    EvidencePhotoUploadSQLAlchemyRepository,
)
from modules.attendance.infra.repositories.record_sqlalchemy_repository import (
    RecordSQLAlchemyRepository,
)
from modules.attendance.infra.repositories.session_sqlalchemy_repository import (
    SessionSQLAlchemyRepository,
)
from modules.room.domain.entities.room import Room
from modules.room.infra.repositories.room_sqlalchemy_repository import RoomSQLAlchemyRepository
from modules.subject_class.domain.entities.subject_class import SubjectClass
from modules.subject_class.infra.repositories.subject_class_sqlalchemy_repository import (
    SubjectClassSQLAlchemyRepository,
)
from shared.enums.upload_status import UploadStatus
from shared.enums.user_role import UserRole
from tests.factories.tenant_factory import TenantFactory
from tests.factories.user_factory import UserFactory
from tests.unit.fakes.fake_storage_service import FakeStorageService

TTL_MINUTES = 120


async def _create_attendance_session(session):
    """Cria a cadeia mínima exigida pelas FKs: tenant, sala, turma e sessão de chamada."""
    tenant = await TenantFactory.create(session)
    room = await RoomSQLAlchemyRepository(session).save(
        Room(tenant_id=tenant.id, name="Sala 1", latitude=-8.0476, longitude=-34.8770)
    )
    subject_class = await SubjectClassSQLAlchemyRepository(session).save(
        SubjectClass(
            tenant_id=tenant.id, name="Turma A", discipline_name="Math", room_id=room.id
        )
    )
    att_session = await SessionSQLAlchemyRepository(session).save(
        AttendanceSession(
            subject_class_id=subject_class.id,
            room_id=room.id,
            day_code="X3KP7Q",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
    )
    return tenant, room, att_session


def _make_upload(session_id: UUID, key: str, age_minutes: int = 0) -> EvidencePhotoUpload:
    return EvidencePhotoUpload(
        session_id=session_id,
        file_key=key,
        url=f"https://fake-r2.dev/{key}",
        uploaded_at=datetime.now(timezone.utc) - timedelta(minutes=age_minutes),
    )


@pytest.mark.asyncio
class TestEvidencePhotoUploadSQLAlchemyRepository:

    async def test_save_and_find_by_id_and_url(self, session):
        """Deve persistir o upload como pending e encontrá-lo por id e por url."""
        _, _, att_session = await _create_attendance_session(session)
        repo = EvidencePhotoUploadSQLAlchemyRepository(session)

        saved = await repo.save(_make_upload(att_session.id, "evidence/s1/a.jpg"))

        assert saved.status == UploadStatus.PENDING
        assert saved.confirmed_at is None
        assert saved.attendance_record_id is None

        by_id = await repo.find_by_id(saved.id)
        assert by_id is not None
        assert by_id.file_key == "evidence/s1/a.jpg"
        assert by_id.session_id == att_session.id

        by_url = await repo.find_by_url("https://fake-r2.dev/evidence/s1/a.jpg")
        assert by_url is not None
        assert by_url.id == saved.id

        assert await repo.find_by_url("https://fake-r2.dev/inexistente.jpg") is None

    async def test_list_by_status_before_returns_only_old_pending(self, session):
        """A consulta do job deve trazer só uploads pending mais antigos que o corte."""
        _, _, att_session = await _create_attendance_session(session)
        repo = EvidencePhotoUploadSQLAlchemyRepository(session)

        old_pending = _make_upload(att_session.id, "evidence/s1/old-pending.jpg", TTL_MINUTES + 30)
        recent_pending = _make_upload(att_session.id, "evidence/s1/recent-pending.jpg", 10)

        # Confirmed sem attendance_record_id: a coluna é nullable, e assim evitamos
        # criar um registro de presença só para satisfazer a FK neste teste.
        old_confirmed = _make_upload(att_session.id, "evidence/s1/old-confirmed.jpg", TTL_MINUTES * 5)
        old_confirmed.status = UploadStatus.CONFIRMED

        old_expired = _make_upload(att_session.id, "evidence/s1/old-expired.jpg", TTL_MINUTES * 5)
        old_expired.expire()

        for upload in (old_pending, recent_pending, old_confirmed, old_expired):
            await repo.save(upload)

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=TTL_MINUTES)
        result = await repo.list_by_status_before(UploadStatus.PENDING, cutoff)

        assert {u.file_key for u in result} == {"evidence/s1/old-pending.jpg"}

    async def test_confirm_links_upload_to_attendance_record(self, session):
        """Confirmar o upload deve persistir status, data e o vínculo com a presença (FK real)."""
        tenant, room, att_session = await _create_attendance_session(session)
        user = await UserFactory.create(session)
        member = await TenantFactory.create_member(
            session, tenant_id=tenant.id, user_id=user.id, role=UserRole.ALUNO
        )
        record = await RecordSQLAlchemyRepository(session).create_record(
            session_id=att_session.id,
            tenant_member_id=member.id,
            latitude=-8.04761,
            longitude=-34.87701,
            room_id=room.id,
            tolerance_radius_meters=50,
        )

        repo = EvidencePhotoUploadSQLAlchemyRepository(session)
        upload = await repo.save(_make_upload(att_session.id, "evidence/s1/b.jpg"))

        upload.confirm(record.id)
        await repo.save(upload)

        reloaded = await repo.find_by_id(upload.id)
        assert reloaded is not None
        assert reloaded.status == UploadStatus.CONFIRMED
        assert reloaded.attendance_record_id == record.id
        assert reloaded.confirmed_at is not None

    async def test_expired_upload_is_no_longer_listed_as_pending(self, session):
        """Depois de expire() + save, o upload sai da consulta de pendentes."""
        _, _, att_session = await _create_attendance_session(session)
        repo = EvidencePhotoUploadSQLAlchemyRepository(session)
        upload = await repo.save(_make_upload(att_session.id, "evidence/s1/c.jpg", TTL_MINUTES + 30))
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=TTL_MINUTES)

        assert len(await repo.list_by_status_before(UploadStatus.PENDING, cutoff)) == 1

        upload.expire()
        await repo.save(upload)

        assert await repo.list_by_status_before(UploadStatus.PENDING, cutoff) == []
        assert (await repo.find_by_id(upload.id)).status == UploadStatus.EXPIRED

    async def test_upload_status_pg_enum_labels_are_lowercase_values(self, session):
        """O tipo nativo upload_status deve ter os values do enum Python, não os names."""
        labels = (
            (
                await session.execute(
                    text(
                        """
                    SELECT e.enumlabel
                    FROM pg_enum e
                    JOIN pg_type t ON e.enumtypid = t.oid
                    WHERE t.typname = 'upload_status'
                    ORDER BY e.enumsortorder
                    """
                    )
                )
            )
            .scalars()
            .all()
        )

        assert labels == ["pending", "confirmed", "expired"]

    async def test_upload_status_pg_enum_rejects_member_name_pending(self, session):
        """O Postgres deve rejeitar o name 'PENDING': só o value 'pending' é válido."""
        with pytest.raises(DBAPIError, match='invalid input value for enum upload_status: "PENDING"'):
            await session.execute(text("SELECT 'PENDING'::upload_status"))

    async def test_cleanup_use_case_with_real_repository(self, session):
        """O use case de limpeza, com o repositório real, persiste o expired no banco."""
        _, _, att_session = await _create_attendance_session(session)
        repo = EvidencePhotoUploadSQLAlchemyRepository(session)
        storage_service = FakeStorageService()

        old = await repo.save(_make_upload(att_session.id, "evidence/s1/old.jpg", TTL_MINUTES + 30))
        recent = await repo.save(_make_upload(att_session.id, "evidence/s1/recent.jpg", 10))

        use_case = CleanupExpiredEvidenceUploadsUseCase(
            upload_repo=repo, storage_service=storage_service
        )
        result = await use_case.execute(CleanupExpiredEvidenceUploadsInput(ttl_minutes=TTL_MINUTES))

        assert result.expired_count == 1
        assert result.failed_count == 0
        assert storage_service.deleted_keys == ["evidence/s1/old.jpg"]
        assert (await repo.find_by_id(old.id)).status == UploadStatus.EXPIRED
        assert (await repo.find_by_id(recent.id)).status == UploadStatus.PENDING
