from uuid import uuid4

import pytest

from modules.attendance.domain.entities.evidence_photo_upload import EvidencePhotoUpload
from shared.enums.upload_status import UploadStatus


def make_upload() -> EvidencePhotoUpload:
    return EvidencePhotoUpload(
        session_id=uuid4(),
        file_key="pending/s1/abc.jpg",
        url="https://fake-r2.dev/pending/s1/abc.jpg",
    )


class TestEvidencePhotoUploadConfirm:

    def test_confirm_without_new_key_keeps_key_and_url(self):
        upload = make_upload()
        record_id = uuid4()

        upload.confirm(record_id)

        assert upload.status == UploadStatus.CONFIRMED
        assert upload.attendance_record_id == record_id
        assert upload.confirmed_at is not None
        assert upload.file_key == "pending/s1/abc.jpg"
        assert upload.url == "https://fake-r2.dev/pending/s1/abc.jpg"

    def test_confirm_with_new_key_and_url_updates_both(self):
        upload = make_upload()

        upload.confirm(
            uuid4(),
            file_key="confirmed/s1/abc.jpg",
            url="https://fake-r2.dev/confirmed/s1/abc.jpg",
        )

        assert upload.status == UploadStatus.CONFIRMED
        assert upload.file_key == "confirmed/s1/abc.jpg"
        assert upload.url == "https://fake-r2.dev/confirmed/s1/abc.jpg"

    def test_confirm_with_only_one_of_key_or_url_is_rejected(self):
        upload = make_upload()

        with pytest.raises(ValueError):
            upload.confirm(uuid4(), file_key="confirmed/s1/abc.jpg")

        with pytest.raises(ValueError):
            upload.confirm(uuid4(), url="https://fake-r2.dev/confirmed/s1/abc.jpg")

        assert upload.status == UploadStatus.PENDING
