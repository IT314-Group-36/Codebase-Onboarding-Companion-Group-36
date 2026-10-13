import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.gettempdir()}/onboarding_test.db"
os.environ["AI_API_URL"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def test_end_to_end():
    with TestClient(app) as c:
        assert c.get("/health").json()["status"] == "ok"

        r = c.post("/api/v1/repos", json={"source": ".."})
        assert r.status_code == 202
        rid = r.json()["id"]

        repo = c.get(f"/api/v1/repos/{rid}").json()
        assert repo["status"] == "ready", repo
        assert repo["file_count"] > 5

        m = c.get(f"/api/v1/repos/{rid}/map").json()
        assert any(mod["name"] == "backend/app/services" for mod in m["modules"])

        f = c.get(f"/api/v1/repos/{rid}/files/backend/app/services/impact.py").json()
        assert "backend/app/models.py" in f["imports"]
        assert "backend/app/routers/qa.py" in f["imported_by"]

        a = c.post(f"/api/v1/repos/{rid}/ask", json={"question": "Where is the impact analysis handled?"}).json()
        assert any("impact" in s["path"] for s in a["sources"])

        i = c.post(f"/api/v1/repos/{rid}/impact", json={"target": "backend/app/models.py"}).json()
        assert i["kind"] == "file" and i["directly_affected"]

        i2 = c.post(f"/api/v1/repos/{rid}/impact", json={"target": "index_repository"}).json()
        assert i2["kind"] == "symbol"

        g = c.get(f"/api/v1/repos/{rid}/graph?level=module").json()
        assert g["edges"]

        src = c.get(f"/api/v1/repos/{rid}/source", params={"path": "backend/app/main.py"}).json()
        assert "FastAPI" in src["content"]

        t = c.get(f"/api/v1/repos/{rid}/onboarding-tasks").json()
        assert len(t["plan"]) == 5

        assert c.delete(f"/api/v1/repos/{rid}").status_code == 204
        assert c.get(f"/api/v1/repos/{rid}").status_code == 404
