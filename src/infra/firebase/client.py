import json
import logging
import os

import firebase_admin
from firebase_admin import credentials

from config.settings import settings

logger = logging.getLogger(__name__)


def _build_credentials() -> credentials.Base:
    """
    Constrói as credenciais do Firebase.

    Prioridade:
      1. FIREBASE_CREDENTIALS_JSON — conteúdo JSON inline (recomendado para produção/CI)
      2. FIREBASE_CREDENTIALS_PATH — caminho para arquivo .json (desenvolvimento local)
    """
    if settings.firebase_credentials_json:
        raw_json = settings.firebase_credentials_json.strip()

        # Remove aspas externas acidentais caso a env tenha sido gravada como '{"..."}' ou "{\"...\":...}"
        if (raw_json.startswith("'") and raw_json.endswith("'")) or (
            raw_json.startswith('"') and raw_json.endswith('"')
        ):
            raw_json = raw_json[1:-1].strip()

        cred_dict = json.loads(raw_json)
        if isinstance(cred_dict, str):
            cred_dict = json.loads(cred_dict)

        # Trata private_key com \n escapado (\\n), muito comum em variáveis de ambiente
        if isinstance(cred_dict, dict) and "private_key" in cred_dict:
            pk = cred_dict["private_key"]
            if isinstance(pk, str) and "\\n" in pk:
                cred_dict["private_key"] = pk.replace("\\n", "\n")

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
        try:
            cred = _build_credentials()
            firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin SDK inicializado com sucesso.")
        except Exception as err:
            logger.error("Falha ao inicializar o Firebase Admin SDK: %s", err, exc_info=True)
            raise
