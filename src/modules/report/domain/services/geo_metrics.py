"""
Funções puras de cálculo geoespacial. NÃO importam FastAPI, SQLAlchemy, nem
nenhuma infraestrutura — podem rodar isoladas em qualquer processo/thread.

NOTA DE DÍVIDA TÉCNICA: esta lógica é conceitualmente do domínio `attendance`
(mesma fórmula usada em record_sqlalchemy_repository.py). Duplicada aqui
deliberadamente para manter os módulos desacoplados dentro do prazo do TCC.
Mover para shared/ em uma refatoração futura.
"""
import math

import numpy as np

EARTH_RADIUS_METERS = 6_371_000.0


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Versão em Python puro — usada dentro de processos (ProcessPoolStrategy)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_METERS * c


def haversine_distance_vectorized(
    lats: np.ndarray, lons: np.ndarray, room_lat: float, room_lon: float
) -> np.ndarray:
    """
    Versão vetorizada com NumPy — usada dentro de threads (ThreadPoolNumpyStrategy).
    Calcula a distância de N pontos para a mesma sala em uma única chamada,
    sem loop Python explícito. As operações trigonométricas do NumPy
    (np.sin, np.cos, np.atan2) são executadas em C e liberam o GIL.
    """
    phi1 = np.radians(lats)
    phi2 = np.radians(room_lat)
    dphi = np.radians(room_lat - lats)
    dlambda = np.radians(room_lon - lons)

    a = np.sin(dphi / 2.0) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2.0) ** 2
    c = 2.0 * np.atan2(np.sqrt(a), np.sqrt(1.0 - a))
    return EARTH_RADIUS_METERS * c


def compute_student_geo_metrics(
    distances: list[float], tolerance_radius_meters: float
) -> dict:
    """Agrega as distâncias recalculadas de um aluno em métricas de auditoria."""
    if not distances:
        return {"avg_distance_meters": 0.0, "confirmations_near_limit": 0}

    avg_distance = sum(distances) / len(distances)
    near_limit_threshold = tolerance_radius_meters * 0.9  # dentro de 90% do limite
    near_limit_count = sum(1 for d in distances if d >= near_limit_threshold)

    return {
        "avg_distance_meters": round(avg_distance, 2),
        "confirmations_near_limit": near_limit_count,
    }
