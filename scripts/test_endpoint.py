"""Hit POST /ask with 10 questions that exercise both locks.

Usage (server already up):
    python -m scripts.test_endpoint
    python -m scripts.test_endpoint --base-url http://localhost:8000

Usage (no server; FastAPI TestClient against this process):
    python -m scripts.test_endpoint --in-process
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Case:
    name: str
    query: str
    role: str
    expect_blocked: bool
    expect_route: str
    # Optional substring that must appear in section names (case-insensitive).
    expect_section_contains: str | None = None
    # Payroll appendix must not be cited (employee salary path).
    forbid_payroll_citation: bool = False
    # Payroll appendix should be cited (admin/hr salary path).
    require_payroll_citation: bool = False


CASES: tuple[Case, ...] = (
    Case(
        name="01_pto_employee",
        query="What is the PTO policy?",
        role="employee",
        expect_blocked=False,
        expect_route="rag",
        expect_section_contains="PTO",
    ),
    Case(
        name="02_hours_employee",
        query="What are the core working hours?",
        role="employee",
        expect_blocked=False,
        expect_route="rag",
        expect_section_contains="Working Hours",
    ),
    Case(
        name="03_remote_employee",
        query="What is the remote work policy?",
        role="employee",
        expect_blocked=False,
        expect_route="rag",
        expect_section_contains="Remote",
    ),
    Case(
        name="04_pay_stub_employee",
        query="How do I request a pay stub?",
        role="employee",
        expect_blocked=False,
        expect_route="rag",
        expect_section_contains="Pay Stub",
    ),
    Case(
        name="05_benefits_employee",
        query="What health benefits does Acme Dynamics offer?",
        role="employee",
        expect_blocked=False,
        expect_route="rag",
        expect_section_contains="Health",
    ),
    Case(
        name="06_it_public",
        query="What is the IT acceptable use policy?",
        role="public",
        expect_blocked=False,
        expect_route="rag",
        expect_section_contains="IT",
    ),
    Case(
        name="07_salary_employee_acl",
        query="What is user X's salary?",
        role="employee",
        expect_blocked=False,
        expect_route="rag",
        forbid_payroll_citation=True,
    ),
    Case(
        name="08_salary_admin_acl",
        query="What is user X's salary?",
        role="admin",
        expect_blocked=False,
        expect_route="rag",
        require_payroll_citation=True,
    ),
    Case(
        name="09_ssn_intent_employee",
        query="what is Jane's SSN?",
        role="employee",
        expect_blocked=True,
        expect_route="privacy_gate",
    ),
    Case(
        name="10_ssn_digits_admin",
        query="please look up 123-45-6789",
        role="admin",
        expect_blocked=True,
        expect_route="privacy_gate",
    ),
)


def _ask_http(base_url: str, query: str, role: str, timeout: float) -> tuple[int, dict[str, Any]]:
    payload = json.dumps({"query": query, "role": role}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/ask",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"answer": body, "error": True}


def _health_http(base_url: str, timeout: float) -> dict[str, Any]:
    req = urllib.request.Request(f"{base_url.rstrip('/')}/health", method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _prepare_in_process() -> Any:
    """Fresh Chroma + fake embeddings so this process does not need MiniLM."""
    import os
    import tempfile
    from pathlib import Path

    os.environ["POLICYRAG_FAKE_EMBEDDINGS"] = "1"
    os.environ["CHROMA_DIR"] = tempfile.mkdtemp(prefix="policyrag-endpoint-")
    os.environ.pop("OPENAI_API_KEY", None)

    from app.config import get_embeddings, pdf_path
    from app.ingest import ingest_pdf
    from scripts.generate_handbook import write_handbook

    get_embeddings.cache_clear()
    pdf = pdf_path()
    if not pdf.is_file():
        write_handbook(pdf)
    ingest_pdf(Path(pdf))

    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def _ask_client(client: Any, query: str, role: str) -> tuple[int, dict[str, Any]]:
    resp = client.post("/ask", json={"query": query, "role": role})
    return resp.status_code, resp.json()


def _sections(body: dict[str, Any]) -> list[str]:
    return [str(c.get("section", "")) for c in body.get("citations") or []]


def _is_payroll_section(section: str) -> bool:
    low = section.lower()
    return "payroll" in low or "appendix a" in low


def evaluate_case(case: Case, status: int, body: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    blocked = bool(body.get("blocked"))
    route = body.get("route")
    if blocked != case.expect_blocked:
        failures.append(f"blocked={blocked} expected {case.expect_blocked}")
    if route != case.expect_route:
        failures.append(f"route={route!r} expected {case.expect_route!r}")
    if case.expect_blocked and status != 403:
        failures.append(f"http {status} expected 403")
    if not case.expect_blocked and status != 200:
        failures.append(f"http {status} expected 200")
    sections = _sections(body)
    if case.expect_section_contains:
        needle = case.expect_section_contains.lower()
        if not any(needle in s.lower() or needle in (body.get("answer") or "").lower() for s in sections):
            # Allow the answer text to carry the heading if citations use a longer title.
            joined = " | ".join(sections) + " " + (body.get("answer") or "")
            if needle not in joined.lower():
                failures.append(f"missing {case.expect_section_contains!r} in citations/answer")
    if case.forbid_payroll_citation and any(_is_payroll_section(s) for s in sections):
        failures.append(f"employee cited payroll appendix: {sections}")
    if case.require_payroll_citation and not any(_is_payroll_section(s) for s in sections):
        failures.append(f"admin did not cite payroll appendix: {sections}")
    return failures


def _print_case(case: Case, status: int, body: dict[str, Any], failures: list[str]) -> None:
    flag = "FAIL" if failures else "PASS"
    sections = ", ".join(_sections(body)) or "-"
    answer = (body.get("answer") or "").replace("\n", " ")
    if len(answer) > 160:
        answer = answer[:157] + "..."
    print(f"[{flag}] {case.name}  role={case.role}  http={status}  "
          f"route={body.get('route')}  blocked={body.get('blocked')}  "
          f"latency_ms={body.get('latency_ms')}")
    print(f"      Q: {case.query}")
    print(f"      citations: {sections}")
    print(f"      A: {answer}")
    for item in failures:
        print(f"      !! {item}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run 10 questions against POST /ask.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument(
        "--in-process",
        action="store_true",
        help="Use FastAPI TestClient instead of HTTP (no running server required).",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    client = None
    if args.in_process:
        client = _prepare_in_process()
        client.__enter__()
        health = client.get("/health").json()
        print(
            f"in-process health ok  collection={health.get('collection')}  "
            f"chunks={health.get('chunk_count')}"
        )
        print()
    else:
        try:
            health = _health_http(args.base_url, args.timeout)
        except Exception as exc:  # noqa: BLE001 — CLI surface
            print(
                f"GET {args.base_url.rstrip('/')}/health failed: {exc}\n"
                "Start the API first:\n"
                "  uvicorn app.main:app --host 0.0.0.0 --port 8000\n"
                "Or run without a server:\n"
                "  python -m scripts.test_endpoint --in-process",
                file=sys.stderr,
            )
            return 2
        print(
            f"health ok  collection={health.get('collection')}  "
            f"chunks={health.get('chunk_count')}"
        )
        print()

    failed = 0
    try:
        for case in CASES:
            if client is not None:
                status, body = _ask_client(client, case.query, case.role)
            else:
                status, body = _ask_http(
                    args.base_url, case.query, case.role, args.timeout
                )
            failures = evaluate_case(case, status, body)
            _print_case(case, status, body, failures)
            if failures:
                failed += 1
    finally:
        if client is not None:
            client.__exit__(None, None, None)

    total = len(CASES)
    print(f"{total - failed}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
