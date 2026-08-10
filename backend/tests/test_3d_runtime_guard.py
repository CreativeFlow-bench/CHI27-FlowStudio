from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_four_stage_hy3d_endpoint_returns_structured_disabled_error() -> None:
    response = client.post(
        "/api/v1/four-stage/runs/any-run/hy3d-candidate",
        json={"image_url": "/files/candidate.png"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "3D_GENERATION_DISABLED"


def test_candidate_hy3d_endpoint_returns_structured_disabled_error() -> None:
    session = client.post("/api/v1/sessions", json={"title": "3D disabled"}).json()

    response = client.post(
        "/api/v1/candidates/any-candidate/hy3d",
        json={"session_id": session["session_id"]},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "3D_GENERATION_DISABLED"
