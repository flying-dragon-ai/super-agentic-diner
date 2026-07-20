import _test_env  # noqa: F401 - activate hermetic defaults before app imports

from fastapi.testclient import TestClient

from app.main import app


def test_local_vite_origin_can_save_office_layout():
    client = TestClient(app)

    for origin in ("http://localhost:5174", "http://localhost:5175"):
        response = client.options(
            "/api/office/layout",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin
        assert response.headers["access-control-allow-credentials"] == "true"
