from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.attendance.application.use_cases.cleanup_expired_evidence_uploads import (
    CleanupExpiredEvidenceUploadsInput,
    CleanupExpiredEvidenceUploadsUseCase,
)
from modules.attendance.domain.entities.evidence_photo_upload import EvidencePhotoUpload
from shared.enums.upload_status import UploadStatus
from tests.unit.fakes.fake_evidence_photo_upload_repository import (
    FakeEvidencePhotoUploadRepository,
)
from tests.unit.fakes.fake_storage_service import FakeStorageService

TTL_MINUTES = 120


def make_upload(age_minutes: int, key: str) -> EvidencePhotoUpload:
    return EvidencePhotoUpload(
        session_id=uuid4(),
        file_key=key,
        url=f"https://fake-r2.dev/{key}",
        uploaded_at=datetime.now(timezone.utc) - timedelta(minutes=age_minutes),
    )


@pytest.mark.asyncio
class TestCleanupExpiredEvidenceUploadsUseCase:

    def _setup(self):
        upload_repo = FakeEvidencePhotoUploadRepository()
        storage_service = FakeStorageService()
        use_case = CleanupExpiredEvidenceUploadsUseCase(
            upload_repo=upload_repo,
            storage_service=storage_service,
        )
        return use_case, upload_repo, storage_service

    async def test_expires_old_pending_uploads_and_deletes_file(self):
        """Upload pending além do TTL tem o arquivo apagado e o registro marcado como expired."""
        use_case, upload_repo, storage_service = self._setup()
        old = make_upload(age_minutes=TTL_MINUTES + 30, key="evidence/s1/old.jpg")
        await upload_repo.save(old)

        result = await use_case.execute(CleanupExpiredEvidenceUploadsInput(ttl_minutes=TTL_MINUTES))

        assert result.expired_count == 1
        assert result.failed_count == 0
        assert storage_service.deleted_keys == ["evidence/s1/old.jpg"]
        saved = await upload_repo.find_by_id(old.id)
        assert saved.status == UploadStatus.EXPIRED

    async def test_keeps_recent_pending_uploads(self):
        """Upload pending dentro do TTL não é tocado."""
        use_case, upload_repo, storage_service = self._setup()
        recent = make_upload(age_minutes=10, key="evidence/s1/recent.jpg")
        await upload_repo.save(recent)

        result = await use_case.execute(CleanupExpiredEvidenceUploadsInput(ttl_minutes=TTL_MINUTES))

        assert result.expired_count == 0
        assert storage_service.deleted_keys == []
        saved = await upload_repo.find_by_id(recent.id)
        assert saved.status == UploadStatus.PENDING

    async def test_ignores_confirmed_uploads_even_when_old(self):
        """Foto já confirmada nunca pode ser apagada, por mais antiga que seja."""
        use_case, upload_repo, storage_service = self._setup()
        confirmed = make_upload(age_minutes=TTL_MINUTES * 10, key="evidence/s1/confirmed.jpg")
        confirmed.confirm(uuid4())
        await upload_repo.save(confirmed)

        result = await use_case.execute(CleanupExpiredEvidenceUploadsInput(ttl_minutes=TTL_MINUTES))

        assert result.expired_count == 0
        assert storage_service.deleted_keys == []
        saved = await upload_repo.find_by_id(confirmed.id)
        assert saved.status == UploadStatus.CONFIRMED

    async def test_storage_failure_keeps_record_pending_and_does_not_stop_batch(self):
        """Falha ao apagar um arquivo mantém o registro pending e não impede os demais."""
        use_case, upload_repo, storage_service = self._setup()
        failing = make_upload(age_minutes=TTL_MINUTES + 30, key="evidence/s1/failing.jpg")
        healthy = make_upload(age_minutes=TTL_MINUTES + 30, key="evidence/s1/healthy.jpg")
        await upload_repo.save(failing)
        await upload_repo.save(healthy)
        storage_service.failing_delete_keys.add("evidence/s1/failing.jpg")

        result = await use_case.execute(CleanupExpiredEvidenceUploadsInput(ttl_minutes=TTL_MINUTES))

        assert result.expired_count == 1
        assert result.failed_count == 1
        assert (await upload_repo.find_by_id(failing.id)).status == UploadStatus.PENDING
        assert (await upload_repo.find_by_id(healthy.id)).status == UploadStatus.EXPIRED
        assert storage_service.deleted_keys == ["evidence/s1/healthy.jpg"]

    async def test_second_run_does_not_reprocess_expired_uploads(self):
        """Depois de expirado, o registro não volta a ser processado."""
        use_case, upload_repo, storage_service = self._setup()
        old = make_upload(age_minutes=TTL_MINUTES + 30, key="evidence/s1/old.jpg")
        await upload_repo.save(old)
        data = CleanupExpiredEvidenceUploadsInput(ttl_minutes=TTL_MINUTES)

        await use_case.execute(data)
        second = await use_case.execute(data)

        assert second.expired_count == 0
        assert storage_service.deleted_keys == ["evidence/s1/old.jpg"]
