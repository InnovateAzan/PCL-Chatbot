from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.main import app


def test_options_chat_allows_local_frontend_origin():
    client = TestClient(app)

    response = client.options(
        "/api/chat",
        headers={
            "Origin": "http://127.0.0.1:5500",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type,x-oneassist-user-id,ngrok-skip-browser-warning",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5500"
    assert response.headers["access-control-allow-credentials"] == "true"
