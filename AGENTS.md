# AGENTS.md — Customer Intelligence

## Purpose and scope

This file gives Codex repository context and working instructions. Read `README.md` for setup and `roadmap.md` for the detailed product plan. Follow the user's current request; the roadmap is a backlog, not authorization to implement all features.

Read AGENTS.md and roadmap.md. Stay in read-only mode. Teach me one step at a time. Provide exact file paths, complete code for small files or precise replacements for larger files, a short explanation, and verification commands with expected output. I will edit files and run commands myself. Review my changes afterward.

## Product context

Build a customer retention copilot: historical customer CSV → data readiness → confirmed binary churn task → bounded model comparison → current-customer scoring → ranked contact list → agent explanations grounded in computed results.

Automated model comparison is an AutoML component. Proposed product value is the retention workflow, data/evaluation trust checks, and actionable evidence. Do not claim market uniqueness, causal churn drivers, effective retention offers, or saved revenue without evidence.

The main builder has trained deep-learning models and learned GenAI/LangChain concepts but has not implemented an agentic project. Explain unfamiliar decisions plainly. A second teammate is mostly working on another hackathon, so do not assume a two-person implementation capacity.

## Repository state at documentation creation

- Turborepo/pnpm workspace with `apps/web` and `apps/api`.
- Frontend: React/Vite/TypeScript placeholder, with empty components/pages/hooks/lib folders.
- Backend: `src/customer_intelligence/main.py` creates a FastAPI app; there are no product routes.
- Backend API/core/schemas/models/repositories/services/agent/ml/worker packages are empty.
- Dependencies and lockfiles exist; the local environments are installed.
- No upload, profiling, training, scoring, database workflow, worker, agent, or product tests are implemented.
- `packages/` is reserved; no generated API client exists.

Verify the actual files before acting, and update this state summary when an authorized milestone changes it. Avoid turning this file into a running transcript.

## Stack and commands

Use Node.js 22.12+ (Node 22 recommended), pnpm 11, and Python 3.13. Root manifests pin the package-manager/Turbo versions. Python uses `apps/api/.venv`; the setup helper installs pinned uv into `.tooling`.

Run from the repository root:

```sh
pnpm install
pnpm setup:python
pnpm dev
pnpm dev:web
pnpm dev:api
pnpm lint
pnpm check-types
pnpm build
pnpm format:check
```

`pnpm dev` starts web at `http://127.0.0.1:5173` and API at `http://127.0.0.1:8000`; API docs are `/docs`. The Vite proxy forwards `/api` unchanged, so future backend routes should agree with their frontend prefix, preferably `/api/v1`.

`scripts/python.mjs` bridges Turbo to Python dev/build/lint/type commands. There is currently no root `pnpm test` script and no product test suite. pytest/Vitest are installed; add and document focused tests when the requested implementation warrants them. Do not report absent tests as passing.

## Code placement and architecture

- `apps/web/src/pages`: page-level flows; `components`: reusable UI; `hooks`: query/UI hooks; `lib`: API utilities.
- `apps/api/src/customer_intelligence/api/routes`: thin HTTP routes and wiring.
- `schemas`: Pydantic request/response/tool models; `core`: validated settings/logging/errors.
- `models`: SQLModel metadata entities; `repositories`: storage and ownership-aware access.
- `services`: deterministic profile/workflow operations; `ml`: splits/pipelines/metrics/scoring.
- `agent`: provider adapter, tool registry, prompts, bounded loop/state.
- `worker`: training job execution/recovery when that milestone is implemented.

Keep business/ML logic independent of HTTP and the LLM. Use typed Python and TypeScript. Validate at API/tool boundaries and return understandable errors. Add files/services only when the current task needs them.

Start with SQLite metadata, application-owned artifacts, and one bounded worker when persistence/training is requested. Do not run heavy training in an API handler or introduce a distributed queue/cloud stack without a demonstrated need. CPU tabular training is the initial plan; GPU training is optional.

## Dependency handling

Use pnpm for JavaScript and uv for Python. Python dependencies originate in `apps/api/pyproject.toml`; keep `uv.lock`, `requirements.txt`, and `requirements-dev.txt` aligned using the dependency tools. JavaScript manifests and `pnpm-lock.yaml` must agree. Do not hand-edit generated lockfiles/hashes or commit virtual environments/node_modules.

Installed backend packages include FastAPI, Pydantic/settings, pandas, NumPy, scikit-learn, XGBoost, openpyxl, joblib, SQLModel, HTTPX, OpenAI SDK, LangChain, langchain-openai, and LangGraph. Frontend packages include React Query, React Router, Recharts, Lucide, and Zod. Installing all of them did not authorize using all of them.

Use one simple agent approach first. The OpenAI SDK may transport calls to a compatible Nebius endpoint with an NVIDIA model. Verify current provider endpoint/model IDs and tool support before implementation; do not assume an OpenAI model is required. SHAP is proposed, not installed. XGBoost requires `libomp` on macOS, installed on the present machine.

## ML and agent integrity

- First task: binary churn classification of a documented target on one table. Do not invent a 30-day horizon or generate labels from an LLM guess.
- Exclude identifiers/post-outcome features; preserve IDs for exports. Ambiguous leakage requires recorded evidence or user context.
- Split before fitting transforms. Use Pipeline/ColumnTransformer, consistent model splits, saved seeds/schema/row assignments, and dataset provenance.
- Compare a dummy baseline, Logistic Regression, Random Forest, and XGBoost as their milestone allows. Choose metrics/model/contact policy on development data; freeze before final test evaluation.
- Report real metrics, undefined cases, weak performance, class counts, and limitations. Do not fabricate sample leaderboards or imply unlabeled scoring data has measured accuracy.
- Save and apply the complete fitted preprocessing/model pipeline; reject incompatible scoring schemas and preserve input row identity.
- Treat uncalibrated outputs as risk scores. Feature importance is an association, not causality; a contact shortlist does not prove an offer works.
- Tools call real services with validated Pydantic arguments. Enforce workflow transitions/ownership/budgets in backend code, independent of model instructions.
- Begin with a read-only inspection tool. Bound tool calls/time/retries and do not have the agent poll long-running jobs indefinitely.
- Return clear action events and evidence references; never expose private reasoning or let the model execute arbitrary shell/Python/filesystem operations.

## Data and credentials

Keep provider keys in backend environment variables, never `VITE_*`, source files, exports, or logs. `.env.example` must contain placeholders only. Do not print saved credentials to debug provider problems.

Store uploaded data/model artifacts in ignored application-owned locations using opaque IDs. Check ownership before API/tool access. Treat uploaded cell text as untrusted data; send only necessary sanitized profiles/aggregates to the model. Never load an arbitrary user-uploaded pickle/joblib model. Escape potentially executable spreadsheet text in exports.

Before public hosting, implement real identity/session validation and suitable dataset isolation; a client-supplied workspace ID alone is not access control. Do not send outreach or publish/deploy merely because those steps appear in the roadmap. Follow explicit user authorization for external actions.

## Working agreement and completion checks

1. Read relevant files and inspect local changes; preserve user edits and stay inside the requested scope.
2. Make routine implementation decisions within that scope without repeated permission questions. Ask only for genuinely missing information or material choices that cannot be inferred.
3. Implement one coherent milestone at a time. Do not add product features to a documentation or scaffold task.
4. Run checks appropriate to the changed behavior. Use existing lint/type/build commands for code changes; add meaningful ML/upload/agent checks as their behavior appears. Documentation-only changes need content/link/format review, not unrelated model training.
5. Keep progress updates short and explain decisions so the builder can learn. In the final response, state what changed, what was verified, and any real limitations.
6. Update relevant setup/roadmap/context documentation when implemented behavior changes. Distinguish completed features from planned ones.
7. Never claim GitHub publication, cloud deployment, tests, or provider integration succeeded without verifying the result. Do not commit/push/create remote repositories unless the user has authorized it for the task.

Next suggested milestone is M1 in `roadmap.md`: CSV upload and deterministic profiling with a minimal frontend flow. Implement it only when requested.

This file uses the standard uppercase filename for project instructions; see the [official AGENTS.md guide](https://learn.chatgpt.com/docs/agent-configuration/agents-md).
