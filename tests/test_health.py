from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_root() -> None:
    """GET / -> Deve retornar status 200 e mensagem confirmando que a API está operacional."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "API is running"}
