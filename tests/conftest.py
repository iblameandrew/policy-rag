"""Session fixtures. Fake embeddings + temp Chroma so tests need no network."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Must run before any app.* import in other test modules.
_CHROMA_TMP = tempfile.mkdtemp(prefix="policyrag-chroma-")
os.environ["POLICYRAG_FAKE_EMBEDDINGS"] = "1"
os.environ["CHROMA_DIR"] = _CHROMA_TMP
os.environ.pop("OPENAI_API_KEY", None)

import pytest  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def handbook_pdf() -> Path:
    from app.config import pdf_path
    from scripts.generate_handbook import write_handbook

    dest = pdf_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    write_handbook(dest)
    return dest


@pytest.fixture(scope="session")
def ingested(handbook_pdf: Path) -> Path:
    from app.ingest import ingest_pdf

    ingest_pdf(handbook_pdf)
    return handbook_pdf
