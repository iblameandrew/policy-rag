"""Runtime configuration. No secrets hardcoded. Env is read at call time."""

from __future__ import annotations

import hashlib
import math
import os
import re
from functools import lru_cache
from pathlib import Path

from langchain_core.embeddings import Embeddings

ROOT = Path(__file__).resolve().parent.parent
COLLECTION_NAME = "employee_handbook"
DOC_ID = "employee_handbook"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 120

SYSTEM_PROMPT = (
    "Answer ONLY from the sources. Cite chunk ids. If sources are missing, say you don't know. "
    "You are not an authorization oracle. If sources don't contain it, you don't know it."
)


def _load_dotenv() -> None:
    path = ROOT / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")


def chroma_dir() -> Path:
    """CHROMA_DIR preferred; CHROMA_PATH accepted as a CI alias."""
    raw = os.getenv("CHROMA_DIR") or os.getenv("CHROMA_PATH") or str(ROOT / "chroma")
    return Path(raw)


def pdf_path() -> Path:
    raw = os.getenv("HANDBOOK_PDF", str(ROOT / "data" / "employee_handbook.pdf"))
    return Path(raw)


def openai_api_key() -> str | None:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    return key or None


def use_fake_embeddings() -> bool:
    return os.getenv("POLICYRAG_FAKE_EMBEDDINGS", "").strip() in {"1", "true", "yes"}


class LexicalEmbeddings(Embeddings):
    """Deterministic bag-of-tokens vectors. Offline, no torch.

    Used in tests (POLICYRAG_FAKE_EMBEDDINGS=1). Production uses MiniLM.
    """

    dim = 128

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in re.findall(r"[a-z0-9]+", text.lower()):
            digest = hashlib.md5(tok.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:2], "little") % self.dim
            vec[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


@lru_cache(maxsize=1)
def get_embeddings() -> Embeddings:
    if use_fake_embeddings():
        return LexicalEmbeddings()
    from langchain_community.embeddings import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
