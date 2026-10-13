from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

CODE = '"""Handles payments."""\nimport stripe\n\ndef create_charge(amount):\n    pass\n'


def test_explain_offline():
    r = client.post("/v1/generate", json={"task": "explain_file", "input": {
        "path": "app/payments.py", "language": "python", "code": CODE,
        "symbols": [{"name": "create_charge", "kind": "function", "signature": "def create_charge(amount)"}]}})
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "offline"
    assert "Handles payments" in body["output"] and "Creates charge" in body["output"]


def test_answer_offline():
    r = client.post("/v1/generate", json={"task": "answer_question", "input": {
        "question": "where are payments handled?",
        "contexts": [{"path": "app/payments.py", "summary": "Handles payments.", "reason": "path matches",
                      "symbols": ["def create_charge(amount)"]}]}})
    assert "app/payments.py" in r.json()["output"]


def test_unknown_task():
    assert client.post("/v1/generate", json={"task": "nope", "input": {}}).status_code == 400
