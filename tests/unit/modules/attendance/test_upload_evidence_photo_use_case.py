from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.attendance.application.use_cases.upload_evidence_photo import (
    UploadEvidencePhotoInput,
    UploadEvidencePhotoUseCase,
)
from modules.attendance.domain.entities.attendance_session import AttendanceSession
from shared.enums.session_status import SessionStatus
from shared.enums.upload_status import UploadStatus
from shared.exceptions import BusinessRuleException, ResourceNotFoundException
from tests.unit.fakes.fake_attendance_session_repository import FakeAttendanceSessionRepository
from tests.unit.fakes.fake_storage_service import FakeStorageService
from tests.unit.fakes.fake_evidence_photo_upload_repository import FakeEvidencePhotoUploadRepository


@pytest.mark.asyncio
class TestUploadEvidencePhotoUseCase:

    async def _setup_fixtures(self, status: SessionStatus = SessionStatus.OPEN):
        session_repo = FakeAttendanceSessionRepository()
        upload_repo = FakeEvidencePhotoUploadRepository()
        storage_service = FakeStorageService()

        subject_class_id = uuid4()
        session = AttendanceSession(
            subject_class_id=subject_class_id,
            day_code="X3KP7Q",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            status=status,
        )
        await session_repo.save(session)

        use_case = UploadEvidencePhotoUseCase(
            session_repo=session_repo,
            upload_repo=upload_repo,
            storage_service=storage_service,
        )

        return use_case, subject_class_id, session, storage_service

    async def test_upload_evidence_photo_success(self):
        """Deve fazer upload, retornar a URL e registrar o upload como pending."""
        use_case, subject_class_id, session, storage_service = await self._setup_fixtures()

        result = await use_case.execute(
            UploadEvidencePhotoInput(
                tenant_id=uuid4(),
                subject_class_id=subject_class_id,
                session_id=session.id,
                file_bytes=b"fake-image-bytes",
                content_type="image/jpeg",
            )
        )

        assert result.url == storage_service.return_url
        assert len(storage_service.uploaded_files) == 1

        saved = list(use_case.upload_repo.uploads.values())
        assert len(saved) == 1
        assert saved[0].status == UploadStatus.PENDING
        assert saved[0].url == result.url
        assert saved[0].session_id == session.id
        assert saved[0].file_key.startswith(f"evidence/{session.id}/")

    async def test_upload_evidence_photo_raises_when_session_not_found(self):
        """Deve lançar ResourceNotFoundException se a sessão não existir para a turma informada."""
        use_case, _, session, storage_service = await self._setup_fixtures()

        with pytest.raises(ResourceNotFoundException, match="Sessão de chamada não encontrada"):
            await use_case.execute(
                UploadEvidencePhotoInput(
                    tenant_id=uuid4(),
                    subject_class_id=uuid4(),  # turma diferente da sessão criada
                    session_id=session.id,
                    file_bytes=b"fake-image-bytes",
                    content_type="image/jpeg",
                )
            )

        assert len(storage_service.uploaded_files) == 0

    async def test_upload_evidence_photo_raises_when_session_not_open(self):
        """Deve lançar BusinessRuleException se a sessão não estiver com status OPEN."""
        use_case, subject_class_id, session, storage_service = await self._setup_fixtures(
            status=SessionStatus.CLOSED
        )

        with pytest.raises(BusinessRuleException, match="não está aberta"):
            await use_case.execute(
                UploadEvidencePhotoInput(
                    tenant_id=uuid4(),
                    subject_class_id=subject_class_id,
                    session_id=session.id,
                    file_bytes=b"fake-image-bytes",
                    content_type="image/jpeg",
                )
            )

        assert len(storage_service.uploaded_files) == 0

    async def test_upload_evidence_photo_raises_on_invalid_mime_type(self):
        """Deve lançar BusinessRuleException se o tipo de arquivo não for suportado."""
        use_case, subject_class_id, session, storage_service = await self._setup_fixtures()

        with pytest.raises(BusinessRuleException, match="Tipo de arquivo não suportado"):
            await use_case.execute(
                UploadEvidencePhotoInput(
                    tenant_id=uuid4(),
                    subject_class_id=subject_class_id,
                    session_id=session.id,
                    file_bytes=b"fake-pdf-bytes",
                    content_type="application/pdf",
                )
            )

        assert len(storage_service.uploaded_files) == 0

    async def test_upload_evidence_photo_raises_when_file_too_large(self):
        """Deve lançar BusinessRuleException se o arquivo exceder 5 MB."""
        use_case, subject_class_id, session, storage_service = await self._setup_fixtures()

        big_file = b"x" * (5 * 1024 * 1024 + 1)

        with pytest.raises(BusinessRuleException, match="Arquivo muito grande"):
            await use_case.execute(
                UploadEvidencePhotoInput(
                    tenant_id=uuid4(),
                    subject_class_id=subject_class_id,
                    session_id=session.id,
                    file_bytes=big_file,
                    content_type="image/jpeg",
                )
            )

        assert len(storage_service.uploaded_files) == 0