from uuid import uuid4

import pytest

from infra.storage.evidence_photo_service import (
    UploadedEvidencePhoto,
    confirmed_key_for,
    upload_evidence_photo,
)
from tests.unit.fakes.fake_storage_service import FakeStorageService


class TestConfirmedKeyFor:

    def test_replaces_pending_prefix_with_confirmed(self):
        assert confirmed_key_for("pending/s1/abc.jpg") == "confirmed/s1/abc.jpg"

    def test_legacy_key_is_returned_unchanged(self):
        """Uploads antigos (evidence/...) já são definitivos e não são promovidos."""
        assert confirmed_key_for("evidence/s1/abc.jpg") == "evidence/s1/abc.jpg"

    def test_only_the_leading_prefix_is_replaced(self):
        assert confirmed_key_for("pending/s1/pending/abc.jpg") == "confirmed/s1/pending/abc.jpg"

    def test_confirmed_key_is_returned_unchanged(self):
        assert confirmed_key_for("confirmed/s1/abc.jpg") == "confirmed/s1/abc.jpg"


@pytest.mark.asyncio
class TestUploadEvidencePhoto:

    async def test_upload_writes_under_pending_prefix(self):
        storage_service = FakeStorageService()
        session_id = uuid4()

        result = await upload_evidence_photo(
            storage_service=storage_service,
            session_id=session_id,
            file_bytes=b"fake-image-bytes",
            content_type="image/png",
        )

        assert isinstance(result, UploadedEvidencePhoto)
        assert result.key.startswith(f"pending/{session_id}/")
        assert result.key.endswith(".png")
        assert storage_service.uploaded_files[0]["key"] == result.key
        assert result.url == storage_service.return_url
