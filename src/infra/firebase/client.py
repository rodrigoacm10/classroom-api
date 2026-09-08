import json
import os

import firebase_admin
from firebase_admin import credentials

from config.settings import settings


def _build_credentials() -> credentials.Base:
    """
    Constrói as credenciais do Firebase.

    Prioridade:
      1. FIREBASE_CREDENTIALS_JSON — conteúdo JSON inline (recomendado para produção/CI)
      2. FIREBASE_CREDENTIALS_PATH — caminho para arquivo .json (desenvolvimento local)
    """
    if settings.firebase_credentials_json:
        cred_dict = json.loads(settings.firebase_credentials_json)
        return credentials.Certificate(cred_dict)

    cred_path = settings.firebase_credentials_path
    if not os.path.exists(cred_path):
        raise FileNotFoundError(
            f"Firebase credentials file not found: {cred_path}. "
            "Set FIREBASE_CREDENTIALS_PATH or FIREBASE_CREDENTIALS_JSON."
        )
    return credentials.Certificate(cred_path)


def init_firebase() -> None:
    """
    Inicializa o Firebase Admin SDK.

    Idempotente: pode ser chamado múltiplas vezes sem erro
    (guarda protegido por firebase_admin._apps).
    """
    if not firebase_admin._apps:
        cred = _build_credentials()
        firebase_admin.initialize_app(cred)
