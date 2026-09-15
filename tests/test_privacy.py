"""Privacy gate: local, rule-based, no vector DB, no LLM."""

from __future__ import annotations

import ast
from pathlib import Path

from app.privacy import evaluate, scrub_ssn_for_log

ROOT = Path(__file__).resolve().parent.parent


def test_jane_ssn_question_is_blocked() -> None:
    decision = evaluate("what is Jane's SSN?")
    assert decision.blocked is True
    assert decision.reason == "ssn_intent"
    assert decision.message is not None
    assert "Social Security" in decision.message


def test_dashed_ssn_is_blocked() -> None:
    decision = evaluate("123-45-6789")
    assert decision.blocked is True
    assert decision.reason == "ssn_intent"


def test_pto_policy_is_not_blocked() -> None:
    decision = evaluate("what is the PTO policy?")
    assert decision.blocked is False
    assert decision.reason is None


def test_spanish_intent_is_blocked() -> None:
    decision = evaluate("cual es el numero de seguro social de Jane?")
    assert decision.blocked is True


def test_compact_nine_digit_with_context_is_blocked() -> None:
    decision = evaluate("lookup ssn 123456789 in payroll")
    assert decision.blocked is True


def test_nine_digit_without_ssn_context_is_not_blocked() -> None:
    decision = evaluate("where is conference room 123456789 located?")
    assert decision.blocked is False


def test_log_scrub_strips_ssn_digits() -> None:
    scrubbed = scrub_ssn_for_log("Jane SSN is 123-45-6789")
    assert "123-45-6789" not in scrubbed
    assert "[SSN]" in scrubbed


def test_privacy_module_does_not_import_chromadb() -> None:
    source = (ROOT / "app" / "privacy.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "chromadb" not in alias.name
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "chromadb" not in node.module
    assert "chromadb" not in source
