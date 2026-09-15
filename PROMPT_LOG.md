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

```
You are a senior AI engineer. Build a complete, runnable Python project in this repo.
... (full take-home spec: PolicyRAG, two locks, layout, Docker, tests) ...
Start now with step 1: create the repo skeleton and scripts/generate_handbook.py.
Wait for me before ingesting if the PDF already exists at data/employee_handbook.pdf.
```

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
