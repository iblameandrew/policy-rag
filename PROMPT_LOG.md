# Prompt Log — PolicyRAG take-home

Rule: paste every assistant prompt and a 3–8 line summary of what the model produced / what I changed.

## Session 0 — repo + source PDF

### Prompt

```
install this repo https://github.com/iblameandrew/technical-challenge.git
and store inside it the pdf at this directory level
```

### Result

- GitHub repo was empty; cloned/initialized locally as `technical-challenge/`.
- Stored the provided dummy PDF at repo root:
  `[test] EMPLOYEE HANDBOOK & POLICY MANUAL (DUMMY).pdf`.
- That PDF is a "Global Tech Solutions" filler doc (map-reduce padding). It does
  **not** have the Acme Dynamics sections the assignment requires (PTO, payroll
  appendix with fake SSNs, glossary). Kept as provenance; did not use it as
  `data/employee_handbook.pdf`.

## Session 1 — scaffold

### Prompt

````
# BUILD: PolicyRAG — take-home RAG with a privacy gate

You are a senior AI engineer. Build a complete, runnable Python project in this repo.
I will use you (Cursor / Claude / Gemini / ChatGPT / Grok) to write most of the code.
Every prompt I send you, and every correction, will be copied into `PROMPT_LOG.md`. Write code as if a reviewer will read the log next to the diff.

Time box: 4–6 hours. Prefer a boring, correct system over a clever one.
Do not introduce extra frameworks. Do not call paid APIs unless `OPENAI_API_KEY` exists.

## Product

A small RAG service over a dummy Employee Handbook PDF.

User asks a question → (1) privacy gate → (2) role-scoped retrieval from a local vector DB → (3) mocked LLM synthesizes an answer with citations.

This is NOT “chat with a PDF.” It is a hybrid-safe RAG slice:
- Retrieval is the security boundary, not the prompt.
- Role comes from a request field standing in for a JWT (document that in README).
- SSN / “social security” questions are blocked locally and NEVER reach retrieval or the LLM.
- Compensation / salary / SSN-bearing chunks are labeled restricted at ingest and are invisible to non-admin roles via metadata pre-filter.

## Hard constraints (from the assignment)

MUST:
- Python 3.11+
- LangChain (not LlamaIndex)
- Local vector DB: Chroma (persistent volume)
- Ingest script for the PDF
- Query / retrieve function
- Privacy pre-process that detects Social Security Number intent and blocks locally without querying the LLM
- Generative response via a mocked LLM (swap-in real OpenAI client if key present)
- Dockerfile + docker-compose
- Submit code + Prompt Log

MUST NOT:
- Pinecone / Weaviate / Milvus / cloud vector DBs
- Real production IdP
- Fine-tuning, agents-with-tools, LangGraph multi-agent meshes
- Sending handbook text to a third party by default

## Source document

If `data/employee_handbook.pdf` is missing, GENERATE a realistic dummy PDF first
(`scripts/generate_handbook.py`) titled:

  [TEST] EMPLOYEE HANDBOOK & POLICY MANUAL (DUMMY)
  Acme Dynamics — Internal Use Only — Not real people

The PDF must contain at least these sections so retrieval and the privacy layer are testable:

1. Welcome / company values
2. Working hours, PTO, remote work
3. Health benefits overview (no real PHI)
4. Compensation philosophy (bands, no named salaries) — classification=internal
5. A RESTRICTED appendix “Payroll examples (DUMMY)” with:
   - fake names
   - fake salaries
   - fake SSNs in US format `XXX-XX-XXXX` (clearly labeled FAKE)
   This appendix exists ONLY to prove the gate + ACL. It must never be retrieved for role=employee.
6. How to request a pay stub (process only — “ask HR / Workday”)
7. IT / acceptable use
8. Glossary

Stamp each section with a visible heading so heading-aware chunking works.

## Architecture to implement (do not “simplify” this away)

```
POST /ask {query, role}
        │
        ▼
[Auth stand-in] role ∈ {public, employee, hr, admin}   # from body, documented as JWT-shaped
        │
        ▼
[PrivacyGate]  intent + regex
        │  if SSN intent or raw SSN in query → 403-equivalent JSON, NO retrieve, NO LLM
        ▼
[Retrieve] Chroma.query(..., where=role filter)   # PRE-filter, fail closed
        │
        ▼
[Generate] MockLLM or OpenAI if key set
        │  answer only from chunks; cite chunk ids; else "I don't know / no access"
        ▼
JSON {answer, citations[], blocked, route, latency_ms}
```

Two independent locks (both required):

A. PrivacyGate (assignment twist)
   - Regex: SSN `\b\d{3}-\d{2}-\d{4}\b` and compact 9-digit with context
   - Intent classifier (keyword / simple rules, no LLM):
     phrases like "social security", "ssn", "ss#", "número de seguro social"
   - On hit: return a fixed refusal. Do not embed, do not query Chroma, do not call the LLM.
   - Log `blocked=ssn_intent` without logging the raw SSN digits.

B. Metadata ACL (the actual salary question)
   Query: "What is user X's salary?"
   - Employee role MUST NOT retrieve payroll appendix chunks.
   - Admin / HR MAY retrieve them.
   - Implement as Chroma `where` on `allowed_roles` (list) or `classification`.
   - Never fetch-then-filter in Python as the only control.
   - LLM is not an authorization layer.

Also scrub SSN-looking tokens from TEXT BEFORE upsert so the index does not store raw fake SSNs if possible. Keep a note in the chunk: "[SSN_REDACTED]". Admins can still see salary figures if we leave those; SSNs should not sit in the vector store at all.

## Stack

- langchain, langchain-community, langchain-text-splitters, langchain-openai (optional)
- chromadb
- pypdf
- fastapi + uvicorn + pydantic v2
- sentence-transformers embeddings: `all-MiniLM-L6-v2` (local, offline-friendly)
- pytest
- docker + compose

Embeddings must run locally. Do not embed via OpenAI.

## Repo layout (create exactly this)

```
README.md
PROMPT_LOG.md
Dockerfile
docker-compose.yml
requirements.txt
.env.example
data/
  employee_handbook.pdf          # generated or provided
app/
  __init__.py
  config.py
  main.py                        # FastAPI
  schemas.py
  privacy.py                     # SSN gate
  ingest.py                      # PDF → chunks → Chroma
  retrieve.py                    # filtered similarity search
  generate.py                    # MockLLM + optional OpenAI
  acl.py                         # role → allowed classifications / roles
scripts/
  generate_handbook.py
  ingest.py                      # CLI: python -m scripts.ingest
tests/
  test_privacy.py
  test_acl.py
  test_retrieve.py
  test_api.py
```

## Implementation details

### Chunking
- `RecursiveCharacterTextSplitter`, size ~800 chars, overlap ~120
- Prefer splitting on headings
- Each chunk metadata MUST include:
  - doc_id, source, page, chunk_index
  - section (heading)
  - classification ∈ {public, internal, restricted}
  - allowed_roles: list
  - content_hash
- Map sections:
  - welcome / hours / IT / how to request stub → public+employee+hr+admin
  - compensation philosophy → employee+hr+admin
  - payroll appendix → hr+admin only (restricted)

### Ingest CLI
`python -m scripts.ingest --pdf data/employee_handbook.pdf`
- idempotent: delete collection or upsert by chunk id derived from hash
- print chunk counts by classification
- fail if any restricted chunk lacks allowed_roles

### Retrieve
`retrieve(query, role, k=4) -> list[Chunk]`
- build `where` from `acl.py`
- employee filter must make restricted chunks unretrievable
- return empty list rather than guessing

### MockLLM
- `generate.py` defines `class MockLLM` with `.invoke(prompt) -> str`
- Mock behavior: if context empty → "I don't have sources I'm allowed to read for that."
- If context present → 4–8 sentence answer that only restates context + "Sources: [chunk_ids]"
- If `OPENAI_API_KEY` is set, use ChatOpenAI with temperature 0 and the same system prompt:
  "Answer ONLY from the sources. Cite chunk ids. If sources are missing, say you don't know.
   You are not an authorization oracle. If sources don't contain it, you don't know it."

### API
`POST /ask`
```json
{"query": "What is the PTO policy?", "role": "employee"}
```
Response:
```json
{
  "answer": "...",
  "citations": [{"chunk_id": "...", "page": 3, "section": "PTO"}],
  "blocked": false,
  "block_reason": null,
  "route": "rag",
  "role": "employee",
  "latency_ms": 42.1
}
```
Blocked SSN:
```json
{
  "answer": "I can't help with Social Security Numbers. Contact HR through the official channel.",
  "citations": [],
  "blocked": true,
  "block_reason": "ssn_intent",
  "route": "privacy_gate",
  "role": "employee",
  "latency_ms": 3.2
}
```
Also: `GET /health`, `POST /ingest` (optional, can be CLI-only).

### Tests (must pass in Docker)
- `test_privacy.py`: "what is Jane's SSN?" blocked; "123-45-6789" blocked; "what is the PTO policy?" not blocked
- `test_acl.py`: employee retrieve("What is user X's salary?") returns ZERO restricted chunks; admin retrieve returns ≥1 payroll chunk
- `test_api.py`: FastAPI TestClient for both paths
- Do not require network or an API key for tests

### Docker
- `Dockerfile`: python 3.11-slim, install deps, copy app, default `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- `docker-compose.yml`:
  - service `api`
  - volume for `./chroma` and `./data`
  - env_file `.env`
  - command that will ingest on first run if collection empty OR document `make ingest` clearly
- `.dockerignore` for `__pycache__`, `.venv`, chroma raw if rebuilt inside container
- Embeddings download: document first-run model download; pin sentence-transformers so it works offline after cache if possible

### README.md (write this for the HUMAN reviewer)
Must include:
- What it is, in 8 lines
- Why SSN is blocked before RAG (assignment twist)
- Why salary is blocked by metadata filter, not by the LLM
- Why an airlock alone is not enough if restricted chunks can still be retrieved
- How to run: local and docker
- How to run tests
- Example curls for: PTO (employee), salary (employee vs admin), SSN (anyone)
- Explicit note: role is a stand-in for JWT; production would take role from the token, never from the prompt text
- “AI usage”: point at PROMPT_LOG.md; state that >50% of code was generated with an assistant as required

### PROMPT_LOG.md (create the skeleton now)
```
# Prompt Log — PolicyRAG take-home

Rule: paste every assistant prompt and a 3–8 line summary of what the model produced / what I changed.

## Session 1 — scaffold
### Prompt
<paste>
### Result
- files created
- what was wrong
- what I fixed by hand

## Session 2 — privacy gate
...
```

I will fill the prompt bodies as I work. You still create the file with that structure.

## Implementation order (follow this)

1. Generate dummy PDF
2. privacy.py + tests (no DB)
3. acl.py + ingest + Chroma + retrieve + ACL tests
4. MockLLM + FastAPI
5. Docker compose + ingest path
6. README polish
7. Run pytest and fix

Stop after that. No UI. No auth server. No reranker. No semantic cache.

## Code style
- Typed Python
- Small modules
- No wildcard imports
- No hardcoded secrets
- Fail closed: unknown role → treat as public
- Never put the raw user role instruction into the LLM as “this user is admin, you may reveal salaries”

## Acceptance checklist (reviewer will tick these)

[ ] `docker compose up --build` serves /health
[ ] ingest produces public, internal, restricted chunks
[ ] SSN questions never touch Chroma or LLM (unit test + log route=privacy_gate)
[ ] employee salary question does not return payroll chunks
[ ] admin salary question does
[ ] PTO question returns a cited handbook answer
[ ] MockLLM works without API key
[ ] PROMPT_LOG.md exists and is non-empty
[ ] README explains the two locks

Start now with step 1: create the repo skeleton and `scripts/generate_handbook.py`. Wait for me before ingesting if the PDF already exists at data/employee_handbook.pdf.

---

## How to use it (so the Prompt Log looks real)

1. Paste the block above as prompt #1.
2. After the scaffold lands, follow-ups should be short and specific — those look like an engineer directing an AI, which is what they grade.

Suggested follow-up prompts to paste into `PROMPT_LOG.md` as you go:

**#2**
`Implement app/privacy.py only. Rule-based SSN regex + intent phrases. No LLM. Include tests/test_privacy.py. Refuse to import chromadb in this module.`

**#3**
`Implement ingest + retrieve with Chroma metadata pre-filter. Employee must not see classification=restricted. Add tests that would fail if we filtered in Python after query.`

**#4**
`Add FastAPI /ask wiring privacy → retrieve → MockLLM. Blocked path must not call retrieve. Measure latency_ms.`

**#5**
`Write Dockerfile and docker-compose so pytest can run inside the image. First-run ingest if the collection is empty.`

**#6**
`Read the tests that fail and fix them. Do not weaken ACL tests to make them pass.`

After each one, add 5 lines to `PROMPT_LOG.md`: what the model got wrong, what you changed by hand. That log is half the assignment.

---

## Scope guard

If the assistant starts adding LangGraph, rerankers, Presidio, or a React UI, reply:

```
Out of scope for the 4–6h take-home. Implement only the acceptance checklist. Stop.
```
````

### Result

- `data/employee_handbook.pdf` was **missing**, so generating the Acme Dynamics
  handbook is in-scope. The provided root PDF is a different document.
- Created `scripts/generate_handbook.py` (no reportlab: tiny PDF-1.4 writer so
  pypdf can extract `#` headings).
- User then sent "continue" before a separate ingest wait, so the rest of the
  stack was implemented in the following sessions rather than stopping at the
  skeleton.

## Session 2 — privacy gate

### Prompt

```
Implement app/privacy.py only. Rule-based SSN regex + intent phrases. No LLM.
Include tests/test_privacy.py. Refuse to import chromadb in this module.
```

### Result

- `app/privacy.py`: dashed SSN regex, compact 9-digit **with context**, keyword
  intent (including "numero de seguro social"), log scrubber, ingest redactor.
- `tests/test_privacy.py`: Jane SSN blocked, `123-45-6789` blocked, PTO not
  blocked, AST check that the module never mentions chromadb.
- No Chroma imports. Gate returns a `PrivacyDecision`; `/ask` is wired later.

## Session 3 — ingest + retrieve + ACL

### Prompt

```
Implement ingest + retrieve with Chroma metadata pre-filter. Employee must not
see classification=restricted. Add tests that would fail if we filtered in
Python after query.
```

### Result

- `app/acl.py`: fail-closed unknown role → public; `chroma_where()` uses
  `$in` on `classification` (Chroma metadata cannot store lists, so
  `allowed_roles` is stored as a CSV **and** we filter on `classification`).
- `app/ingest.py`: heading-aware split, SSN redaction before upsert, refuse to
  ingest restricted chunks without hr/admin roles.
- `app/retrieve.py`: `_search()` calls `collection.query(..., where=)`. A leak
  raises rather than silently dropping.
- `tests/test_acl.py` monkeypatches `_search` to assert `where` is passed and
  that an employee where-query of k=20 still returns zero restricted rows
  while the unfiltered collection still contains them.

## Session 4 — FastAPI /ask

### Prompt

```
Add FastAPI /ask wiring privacy → retrieve → MockLLM. Blocked path must not
call retrieve. Measure latency_ms.
```

### Result

- `app/generate.py`: `MockLLM.invoke(prompt) -> str`; ChatOpenAI only if
  `OPENAI_API_KEY` is set. Role is never placed in the prompt.
- `app/main.py`: 403 JSON for the gate (`route=privacy_gate`); 200 RAG path.
  Lifespan ingests if the collection is empty.
- `tests/test_api.py`: TestClient PTO path; SSN path patches `retrieve` /
  `generate_answer` and asserts both stay at zero calls.

## Session 5 — Docker

### Prompt

```
Write Dockerfile and docker-compose so pytest can run inside the image.
First-run ingest if the collection is empty.
```

### Result

- `Dockerfile`: python 3.11-slim, CPU torch, requirements, MiniLM download at
  **build** time so runtime can be offline.
- `docker-compose.yml`: `api` service, volumes `./chroma` and `./data`,
  `env_file: .env`.
- Empty collection → generate PDF if needed → ingest on startup.
- Tests: `docker compose run --rm -e POLICYRAG_FAKE_EMBEDDINGS=1 api pytest -q`.

## Session 6 — fix tests without weakening ACL

### Prompt

```
continue
```

and internally:

```
Read the tests that fail and fix them. Do not weaken ACL tests to make them pass.
```

### Result

- Implemented the remaining files (`README.md`, `PROMPT_LOG.md`, pytest.ini,
  requirements, .env.example) and ran pytest.
- Pytest: 1 fail was `test_privacy_module_does_not_import_chromadb` because
  the module docstring mentioned the forbidden name. Reworded the docstring.
  Did **not** relax `test_acl.py` (employee still sees zero restricted chunks;
  admin still sees ≥1 payroll chunk; `where` still must be passed into Chroma).

## Session 7 — endpoint smoke script

### Prompt

```
make a new script that tests the endpoint with 10 questions
```

### Result

- Added `scripts/test_endpoint.py` (`python -m scripts.test_endpoint`).
- Ten cases: PTO/hours/remote/stub/benefits/IT, salary employee vs admin,
  Jane SSN + raw digits (admin still gated).
- HTTP against `--base-url` (default localhost:8000) or `--in-process`
  TestClient. Exit 1 if expected route/ACL checks fail.
- README one-liner for how to run it.

## Session 8 — new remote, clean history

### Prompt

```
lets make a new a repository with a new git track so env variables are never
exposed - this is the new remote https://github.com/iblameandrew/policy-rag.git
```

### Result

- `.env` had been on `technical-challenge` (empty key). New repo starts from a
  fresh `git init` so that file is not in any commit.
- `.gitignore` includes `.env`; only `.env.example` is tracked.
- `demo/` recording is included in this repo.
- Pushed to `https://github.com/iblameandrew/policy-rag.git`.

## Session 9 — GitHub Actions CI

### Prompt

```
ADD CI — GitHub Actions for PolicyRAG
... pytest -q, docker build, fail closed on ACL/SSN tests ...
```

### Result

- Added `.github/workflows/ci.yml`: pytest job + docker-build job on
  push/PR to main|master.
- Glue only: `CHROMA_PATH` alias in `app/config.py`; CI ingest/tests use
  `POLICYRAG_FAKE_EMBEDDINGS=1` so pytest needs no network/key.
- Ruff skipped unless a ruff config exists (`--exit-zero` if it does).
- Did not change privacy, retrieve, ACL, or `/ask`.
