import json
from unittest.mock import MagicMock, patch

import pytest

from infra.firebase.client import _build_credentials, init_firebase


class TestFirebaseClient:
    """
    Testes unitários para inicialização do Firebase Admin SDK e resolução de credenciais.
    """

    def test_build_credentials_from_json_string(self):
        """Deve construir Certificate a partir de JSON válido em FIREBASE_CREDENTIALS_JSON."""
        fake_cred = {
            "type": "service_account",
            "project_id": "test-project",
            "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgk\n-----END PRIVATE KEY-----\n",
            "client_email": "test@test-project.iam.gserviceaccount.com",
        }
        with patch("config.settings.settings.firebase_credentials_json", json.dumps(fake_cred)):
            with patch("firebase_admin.credentials.Certificate") as mock_cert:
                _build_credentials()
                mock_cert.assert_called_once()
                arg = mock_cert.call_args.args[0]
                assert arg["project_id"] == "test-project"

    def test_build_credentials_strips_outer_quotes_and_escaped_newlines(self):
        """Deve remover aspas externas e converter '\\n' literal para quebra de linha real."""
        raw_json_with_quotes = (
            '\'{"type": "service_account", "project_id": "test-quoted", '
            '"private_key": "-----BEGIN PRIVATE KEY-----\\\\nMIIEvg\\\\n-----END PRIVATE KEY-----\\\\n"}\''
        )
        with patch("config.settings.settings.firebase_credentials_json", raw_json_with_quotes):
            with patch("firebase_admin.credentials.Certificate") as mock_cert:
                _build_credentials()
                mock_cert.assert_called_once()
                arg = mock_cert.call_args.args[0]
                assert arg["project_id"] == "test-quoted"
                assert "\\n" not in arg["private_key"]
                assert "\n" in arg["private_key"]

    def test_build_credentials_from_file_path_when_exists(self, tmp_path):
        """Deve construir Certificate a partir de arquivo quando FIREBASE_CREDENTIALS_JSON está vazio e arquivo existe."""
        cred_file = tmp_path / "firebase-service-account.json"
        cred_file.write_text('{"type": "service_account"}')

        with patch("config.settings.settings.firebase_credentials_json", ""):
            with patch("config.settings.settings.firebase_credentials_path", str(cred_file)):
                with patch("firebase_admin.credentials.Certificate") as mock_cert:
                    _build_credentials()
                    mock_cert.assert_called_once_with(str(cred_file))

    def test_build_credentials_raises_file_not_found_when_missing(self):
        """Deve levantar FileNotFoundError quando nem JSON nem arquivo existem."""
        with patch("config.settings.settings.firebase_credentials_json", ""):
            with patch(
                "config.settings.settings.firebase_credentials_path", "non_existent_path.json"
            ):
                with pytest.raises(FileNotFoundError, match="Firebase credentials file not found"):
                    _build_credentials()

    def test_init_firebase_idempotent_when_already_initialized(self):
        """Não deve reinicializar se firebase_admin._apps já possui instâncias."""
        with patch("firebase_admin._apps", {"[DEFAULT]": MagicMock()}):
            with patch("infra.firebase.client._build_credentials") as mock_build:
                init_firebase()
                mock_build.assert_not_called()

    def test_init_firebase_initializes_when_apps_empty(self):
        """Deve chamar initialize_app com as credenciais quando _apps estiver vazio."""
        with patch("firebase_admin._apps", {}):
            with patch("infra.firebase.client._build_credentials", return_value="dummy_cred"):
                with patch("firebase_admin.initialize_app") as mock_init:
                    init_firebase()
                    mock_init.assert_called_once_with("dummy_cred")
