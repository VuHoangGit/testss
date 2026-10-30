"""CORS cho origin IP tư nhân trong LAN — mở app trên điện thoại qua IP máy."""

from fastapi.testclient import TestClient


def test_cors_allows_lan_origin(client: TestClient) -> None:
    resp = client.get("/openapi.json", headers={"Origin": "http://192.168.1.20:53123"})
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "http://192.168.1.20:53123"


def test_cors_allows_localhost_origin(client: TestClient) -> None:
    resp = client.get("/openapi.json", headers={"Origin": "http://localhost:53123"})
    assert resp.headers["access-control-allow-origin"] == "http://localhost:53123"


def test_cors_rejects_public_origin(client: TestClient) -> None:
    resp = client.get("/openapi.json", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in resp.headers
