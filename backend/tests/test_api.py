import os

os.environ["RI_DATABASE_URL"] = "sqlite:///./test_api.db"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def setup_module(_):
    if os.path.exists("test_api.db"):
        os.remove("test_api.db")


def test_end_to_end_over_http():
    with TestClient(app) as client:
        state = client.get("/api/state").json()
        assert len(state["tables"]) == 8 and len(state["staff"]) == 4

        with client.websocket_connect("/ws") as ws:
            r = client.post("/api/events", json=[
                {"type": "table.occupied", "table": "2", "camera_id": "cam-1", "data": {"party_size": 2}},
                {"type": "table.vacated", "table": "2", "camera_id": "cam-1"},
            ])
            assert r.status_code == 202
            kinds = {ws.receive_json()["type"] for _ in range(4)}
            assert {"table", "task"} <= kinds

        task = next(t for t in client.get("/api/state").json()["tasks"] if t["type"] == "clean_table")
        staff_id = state["staff"][0]["id"]
        assert client.post(f"/api/tasks/{task['id']}/assign", json={"staff_id": staff_id}).status_code == 200
        client.post("/api/events", json=[
            {"type": "table.attended", "table": "2", "camera_id": "cam-1"},
            {"type": "table.surface", "table": "2", "camera_id": "cam-1", "data": {"items": 0}},
        ])
        done = client.post(f"/api/tasks/{task['id']}/complete").json()
        assert done["status"] == "verified"
        assert client.post(f"/api/tasks/{task['id']}/complete").status_code == 409

        client.post("/api/pos/orders", json={"pos_ref": "T-1", "table": "2"})
        pos = client.get("/api/state").json()["integrations"]
        assert pos and pos[0]["id"] == "pos" and pos[0]["online"]

        report = client.get("/api/analytics").json()
        assert report["cleaning"]["tables_cleaned"] >= 1
