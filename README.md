# Customer Intelligence

A customer retention copilot with a working P0/P1 backend and a React/Vite marketing frontend.
Historical labeled sheet → confirmed task → model comparison → saved pipeline → current-customer
risk ranking → CSV shortlist. The Nebius/NVIDIA assistant uses tools to explain computed evidence
and can queue an explicitly authorized training plan.

## Start locally

Use Python 3.13, Node 22.12+ and pnpm 11. On macOS XGBoost requires `brew install libomp`.

```sh
pnpm install
pnpm setup:python
```

On this machine the default Node 25 executable currently fails with a missing `libsimdjson` library.
The installed Node 22 works. Select it in each terminal before the pnpm commands:

```sh
export PATH="/opt/homebrew/opt/node@22/bin:$PATH"
```

For assistant requests, add the credentials/model you already verified to `apps/api/.env`.
Use `apps/api/.env.example` as a reference; do not overwrite your existing `.env`.
Upload, training and scoring work without provider credentials.

Run these in **two separate terminals** from the project root:

```sh
pnpm dev:api
```

```sh
pnpm worker:api
```

API: <http://127.0.0.1:8000>; interactive API contracts: <http://127.0.0.1:8000/docs>.
The worker is required: submitting a job only queues it. It supervises one CPU job at a time.
`pnpm dev` also starts the marketing frontend at <http://127.0.0.1:5173>.
Landing, features and pricing pages are implemented. Login/signup are disabled design previews.
See [the frontend guide](docs/frontend.md). Core product screens remain planned.

If using Python directly, activate **`apps/api/.venv/bin/activate`**, not a root `venv`.

```sh
cd apps/api
source .venv/bin/activate
python -m uvicorn customer_intelligence.main:app --host 127.0.0.1 --port 8000
# In another terminal with the same environment:
python -m customer_intelligence.worker
```

## Repeatable backend demo

With API and worker running, from the project root:

```sh
apps/api/.venv/bin/python apps/api/demo.py
```

This generates explicitly synthetic labeled history and a separate unlabeled customer sheet,
uploads them, trains the four model families, computes validation diagnostics, evaluates the frozen
winner once, scores current customers, and saves the HTML report and contact CSV under ignored
`.data/demo-output`. It prints the actual IDs and measured metrics. It adds new demo records;
it does not alter existing customer uploads or saved runs. It does not call the model provider.
Add `--with-agent` to explicitly exercise Nebius using your configured model and API credits.
If `CI_API_TOKEN` is configured, export that same variable before running the demo.

See [the backend walkthrough](docs/backend.md) for individual requests, the architecture,
P1 options, errors, and limitations. See [roadmap.md](roadmap.md) for product scope and
[AGENTS.md](AGENTS.md) for coding context.

## Implemented backend

- CSV/XLSX import, bounded preview/profile, binary-label readiness and immutable confirmed tasks.
- Reproducible stratified train/validation/test splits; train-only preprocessing and saved schema.
- Dummy baseline, Logistic Regression, Random Forest, XGBoost; up to eight extra fixed trials.
- Durable jobs, idempotency, queue/time limits, cancellation, process supervision and restart recovery.
- Pipeline/version/checksum provenance, frozen test evaluation, saved runs and comparable-run checks.
- Batch scoring, deterministic ranking, contact budget, risk × value option and safe CSV export.
- P1 diagnostics: contact curves, Brier/reliability bins, permutation importance, segments with
  count/uncertainty guards, numeric business heuristic, synthetic leakage demonstration.
- Optional sigmoid calibration creates a new pipeline without refitting preprocessing or using test
  labels; per-customer reference perturbations show model sensitivity with explicit limitations.
- Downloadable experiment HTML, evidence-linked bounded assistant, saved conversations,
  private-workspace API token and dependency-aware data deletion.

## Checks and dependency management

```sh
pnpm test:api
pnpm --filter @ci/api lint
pnpm --filter @ci/api check-types
pnpm --filter @ci/api build
```

Tests use isolated synthetic data, real CPU training/pipeline reloads and a fake provider transport;
they do not transmit customer sheets or evaluate your saved Telco test partition.
Python packages originate in `apps/api/pyproject.toml`, are locked in `uv.lock`, and are exported
in `requirements*.txt`. Keep these synchronized with uv. The worker currently supports macOS/Linux
because its single-worker lock uses `fcntl`.

## Honest boundaries

This release supports **binary classification on one static customer table**. It cannot infer a
valid future churn horizon or independently establish feature availability. It uses a stratified
random split; dated or repeated-customer data needs a separate time/group evaluation implementation.
The selected model is the best measured candidate under this budget, not a globally optimal model.

This is one private local workspace, not a publicly deployable multi-tenant SaaS. Optional bearer
authentication does not replace user accounts, tenancy or authorization. Public hosting, CRM/outreach,
monitoring, regression and P2 features are future work. The marketing frontend is implemented; account access remains unimplemented.

Assistant calls transmit profiles (excluding raw previews), task settings, run/analysis metrics and
chat history to Nebius. Do not put credentials or unnecessary personal information into chat or
column names. Uploaded sheets and full scored-customer rows are not sent automatically. Numerical
services work independently of GenAI; the provider interprets evidence and chooses allowed tools.
LangChain/LangGraph are installed but this agent uses the OpenAI-compatible SDK directly. Qdrant
is not required for these structured facts. Adding policy-document retrieval later is a separate feature.
