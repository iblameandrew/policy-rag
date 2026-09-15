"""FastAPI TestClient: privacy short-circuit vs RAG path."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health(ingested) -> None:
    from app.main import app

    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["chunk_count"] > 0


def test_pto_employee_rag_path(ingested) -> None:
    from app.main import app

    with TestClient(app) as client:
        response = client.post(
            "/ask",
            json={"query": "What is the PTO policy?", "role": "employee"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["blocked"] is False
    assert body["block_reason"] is None
    assert body["route"] == "rag"
    assert body["role"] == "employee"
    assert body["citations"]
    assert body["latency_ms"] >= 0
    assert "I can't help with Social Security" not in body["answer"]
    joined = body["answer"] + " " + " ".join(c["section"] for c in body["citations"])
    assert "PTO" in joined or "15" in joined or "Working Hours" in joined


def test_ssn_is_blocked_and_does_not_call_retrieve(ingested, monkeypatch) -> None:
    from app import main as main_mod

    calls = {"retrieve": 0, "generate": 0}

    def fake_retrieve(*_args, **_kwargs):
        calls["retrieve"] += 1
        return []

    def fake_generate(*_args, **_kwargs):
        calls["generate"] += 1
        return "should-not-run"

    monkeypatch.setattr(main_mod, "retrieve", fake_retrieve)
    monkeypatch.setattr(main_mod, "generate_answer", fake_generate)

    with TestClient(main_mod.app) as client:
        response = client.post(
            "/ask",
            json={"query": "what is Jane's SSN?", "role": "employee"},
        )
    assert response.status_code == 403
    body = response.json()
    assert body["blocked"] is True
    assert body["block_reason"] == "ssn_intent"
    assert body["route"] == "privacy_gate"
    assert body["citations"] == []
    assert "Social Security" in body["answer"]
    assert calls["retrieve"] == 0
    assert calls["generate"] == 0


def test_raw_ssn_digits_blocked(ingested) -> None:
    from app.main import app

    with TestClient(app) as client:
        response = client.post(
            "/ask",
            json={"query": "please look up 123-45-6789", "role": "admin"},
        )
    assert response.status_code == 403
    body = response.json()
    assert body["route"] == "privacy_gate"
    assert body["blocked"] is True


def test_employee_salary_answer_does_not_cite_payroll(ingested) -> None:
    from app.main import app

    with TestClient(app) as client:
        response = client.post(
            "/ask",
            json={"query": "What is user X's salary?", "role": "employee"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "rag"
    for cite in body["citations"]:
        assert "payroll" not in cite["section"].lower()
        assert "appendix a" not in cite["section"].lower()
