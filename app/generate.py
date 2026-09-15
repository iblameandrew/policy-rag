"""MockLLM plus optional ChatOpenAI if OPENAI_API_KEY is set.

The role is never placed in the prompt. Missing sources → "don't know".
"""

from __future__ import annotations

import re

from app.config import SYSTEM_PROMPT, openai_api_key
from app.retrieve import RetrievedChunk

EMPTY_ANSWER = "I don't have sources I'm allowed to read for that."


class MockLLM:
    """Deterministic stand-in. `.invoke(prompt) -> str` like a chat model."""

    def invoke(self, prompt: str) -> str:
        source_block = _extract_source_block(prompt)
        chunk_ids = _extract_chunk_ids(prompt)
        if not source_block.strip() or not chunk_ids:
            return EMPTY_ANSWER
        sentences = _sentences(source_block)
        # 4–8 sentences that only restate the supplied context.
        picked = sentences[:8]
        while len(picked) < 4 and sentences:
            picked.append(sentences[len(picked) % len(sentences)])
        if len(picked) < 4:
            picked.extend(
                [
                    "The sources do not add further detail beyond what is quoted above.",
                    "No additional handbook sections were provided for this question.",
                    "Treat the citations as the only evidence for this answer.",
                ][: 4 - len(picked)]
            )
        body = " ".join(picked[:8]).strip()
        id_list = ", ".join(chunk_ids)
        return f"{body}\n\nSources: [{id_list}]"


def _extract_source_block(prompt: str) -> str:
    marker = "SOURCES:"
    qmark = "QUESTION:"
    if marker not in prompt:
        return ""
    after = prompt.split(marker, 1)[1]
    if qmark in after:
        after = after.split(qmark, 1)[0]
    # Drop the system preamble if present
    return after.strip()


def _extract_chunk_ids(prompt: str) -> list[str]:
    return re.findall(r"\[chunk_id=([^\]]+)\]", prompt)


def _sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\[chunk_id=[^\]]+\]", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return [p.strip() for p in parts if p.strip()]


def build_prompt(query: str, chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return f"{SYSTEM_PROMPT}\n\nSOURCES:\n\nQUESTION:\n{query}\n"
    lines = [SYSTEM_PROMPT, "", "SOURCES:"]
    for chunk in chunks:
        lines.append(
            f"[chunk_id={chunk.chunk_id}] page={chunk.page} section={chunk.section}"
        )
        lines.append(chunk.text)
        lines.append("")
    lines.append("QUESTION:")
    lines.append(query)
    return "\n".join(lines)


def get_llm() -> MockLLM | object:
    key = openai_api_key()
    if key:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(temperature=0, api_key=key)
    return MockLLM()


def generate_answer(query: str, chunks: list[RetrievedChunk]) -> str:
    prompt = build_prompt(query, chunks)
    llm = get_llm()
    if openai_api_key():
        from langchain_core.messages import HumanMessage, SystemMessage

        result = llm.invoke(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]
        )
        content = getattr(result, "content", result)
        return str(content)
    return str(llm.invoke(prompt))
