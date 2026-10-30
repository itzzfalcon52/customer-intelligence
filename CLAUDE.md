# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@AGENTS.md

AGENTS.md above is the authoritative project brief (scope authorizations, ML/agent integrity rules,
credential handling). This file only adds what is useful for navigating and running the code.

## Commands

All commands run from the repository root. Python commands go through `scripts/python.mjs`, which
runs `apps/api/.venv/bin/python` with `cwd=apps/api` and forwards extra arguments.

```sh
pnpm setup:python          # create apps/api/.venv (pinned uv in .tooling)
pnpm setup:backend         # configure apps/backend/.env for Neon + INTERNAL_API_SECRET
pnpm dev                   # turbo: web :5173, Better Auth backend :3001, FastAPI :8000
pnpm worker:api            # training worker — separate terminal, required for jobs
pnpm lint | check-types | build | format:check

pnpm test:api                                   # pytest tests -q
# pnpm scripts don't forward extra args to pytest; call the venv directly for a subset:
cd apps/api && .venv/bin/python -m pytest tests/test_workflow.py -q        # single file
cd apps/api && .venv/bin/python -m pytest tests/test_agent.py -k name -q   # single test
pnpm test:backend                               # tsx --test; DB tests skip without AUTH_TEST_DATABASE_URL
pnpm --filter @ci/web test                      # vitest (workspace api/stream tests)
pnpm eval:agent            # replay recorded agent evals offline (free); exit 1 if any scenario fails
pnpm eval:agent:live       # same against Nebius (spends credits); :record also refreshes cassettes
```

Python lint is `ruff check src tests demo.py`; types are `mypy src/customer_intelligence`. The ruff
format task deliberately excludes `ml/preprocessing.py` — saved pipelines fingerprint that file, so
any edit (including reformatting) invalidates existing pipelines. It must stay unchanged.

For curl/CLI learning flows without a browser session: `CI_AUTH_MODE=private pnpm dev:api` and
`CI_AUTH_MODE=private pnpm worker:api` (loopback only; never alongside the authenticated app).

## Architecture

Three apps in a pnpm/Turbo monorepo:

- **apps/web** — React 19 + Vite. Marketing pages in `src/pages`; the authenticated product lives
  in `src/workspace` (TanStack Query in `queries.ts`/`retention-hooks.ts`, typed fetch client in
  `api.ts`, Zustand UI prefs in `store.ts`). Vite proxies `/api/auth` and `/api/backend` → :3001
  and `/api/v1` → :8000, so new Python routes belong under `/api/v1`.
- **apps/backend** — Express 5 + Better Auth 1.7.7 + Prisma (PostgreSQL/Neon), organisation plugin.
  Owns users/sessions only. Exposes `/internal/identity`, authenticated by `INTERNAL_API_SECRET`.
- **apps/api** — FastAPI + SQLModel/SQLite + scikit-learn/XGBoost, package `customer_intelligence`.

**Auth bridge:** FastAPI never reads the auth DB. `core/identity.py` forwards only the Better Auth
session cookie to the backend's `/internal/identity` with the bridge secret and gets a `user_id`;
metadata and `.data` artifacts are then scoped to that personal account. Legacy (pre-account) data
is kept separate and is not auto-imported.

**ML flow (Python):** upload → `services/profiling` → target check → immutable task (`services/tasks`)
→ split/plan → `POST /jobs/train` enqueues an idempotent job → `worker/` claims it, runs training
(`services/training`, `ml/*`) in a child process with timeout/cancel → run with final test evaluation
→ scoring/export, analysis, calibration, retention policies (`ml/policy.py`, `services/retention*`).
Routes in `api/routes` stay thin; logic lives in `services`/`ml`, independent of HTTP and the LLM.

**Agent:** every model call goes through `agent/llm.py` (`LLMGateway`: retries, repair, fast/primary
routing, usage). `agent/tracing.py` installs a per-operation `Tracer` in a contextvar so nested calls
(an action tool's own model call) join one trace, saved as `AgentTrace`/`AgentSpan` even on failure.
`agent/workflow.py` is the bounded tool loop (request-scoped resource IDs, budgets counted from the
tracer). Prompts are versioned files in `agent/prompts/`; add a new version instead of editing one.
`agent/graph/investigator.py` is a LangGraph investigation (model plans and writes; analyses in
`ml/investigation.py` and verification in `agent/verification.py` are deterministic). Number
grounding (`agent/grounding.py`) and the causal-wording check gate both investigations and chat
answers. `apps/api/evals/` holds the eval harness and cassettes (`--live --repeat N` for rates). Tests mock the provider, so don't call the
live provider without reason.

## Reference docs

- `docs/backend.md` — job/evaluation/agent boundaries and curl walkthrough (read before changing them)
- `docs/retention-studio.md` — October 15 retention features, CV and decision policies (supersedes older notes)
- `docs/auth.md` — Better Auth setup, test-database rules, bridge secret
- `docs/workspace.md` — frontend feature coverage and verification
- `docs/product-strategy.md` — approved M1–M6 direction; only M1 is authorized so far
- `roadmap.md` — backlog, not authorization
