import numpy as np

from modules.report.domain.services.geo_metrics import (
    compute_student_geo_metrics,
    haversine_distance,
    haversine_distance_vectorized,
)


def test_haversine_distancia_zero_no_mesmo_ponto():
    """Deve retornar 0 metros quando origem e destino são o mesmo ponto."""
    assert haversine_distance(-8.05, -34.87, -8.05, -34.87) == 0.0


def test_haversine_distancia_conhecida_aproximada():
    """Deve calcular ~6 km entre Recife e Olinda (tolerância de 500 m)."""
    d = haversine_distance(-8.0476, -34.8770, -7.9997, -34.8552)
    assert 5_000 < d < 7_000


def test_versao_vetorizada_bate_com_versao_pura():
    """Deve produzir as mesmas distâncias na versão NumPy e na versão em Python puro."""
    lats = np.array([-8.0476, -8.05, -8.06])
    lons = np.array([-34.8770, -34.88, -34.89])
    vetor = haversine_distance_vectorized(lats, lons, -8.05, -34.88)
    puro = [haversine_distance(lat, lon, -8.05, -34.88) for lat, lon in zip(lats, lons)]
    assert np.allclose(vetor, puro, atol=0.01)


def test_geo_metrics_sem_distancias_retorna_zeros():
    """Deve devolver média 0 e zero confirmações no limite quando não há distâncias."""
    assert compute_student_geo_metrics([], 50.0) == {
        "avg_distance_meters": 0.0,
        "confirmations_near_limit": 0,
    }


def test_geo_metrics_conta_confirmacoes_no_limite():
    """Deve contar como 'perto do limite' as distâncias ≥ 90% do raio de tolerância."""
    result = compute_student_geo_metrics([10.0, 45.0, 50.0], tolerance_radius_meters=50.0)
    assert result["avg_distance_meters"] == 35.0
    assert result["confirmations_near_limit"] == 2  # 45 e 50 estão ≥ 45 (90% de 50)
