> October 15 update: see [Retention Studio](retention-studio.md) for the active AI actions,
> automatic briefings/drafts, training CV and decision policies. This supersedes older limitations below.

# Backend walkthrough and learning guide

## How the pieces work

**FastAPI** exposes HTTP endpoints. **Pydantic** validates incoming fields and outgoing contracts.
**SQLite** stores metadata, tasks, jobs and conversations. **SQLAlchemy** is the database toolkit;
**SQLModel** combines its table/ORM mapping with Pydantic-style models. SQLAlchemy is not the database.
Large customer files and fitted pipelines live in ignored `.data`, referenced by opaque UUIDs.

Services calculate facts deterministically. The ML package fits transformations on training rows only.
The worker claims a queued job, launches an isolated child process, updates progress, and stops the
child on cancellation or timeout. Failed or interrupted jobs remain visible; retry with a **new**
idempotency key. Repeating the same key and identical payload returns the same job; changing the
payload under that key returns 409. One worker holds the data-directory lock. Restarting it marks
unfinished jobs failed/cancelled rather than pretending they finished.

The assistant calls the configured NVIDIA model via Nebius with validated function tools. It cannot
execute Python/shell or access arbitrary files. Each request scopes the permitted resource IDs,
requires supporting tools before answering, and permits at most six model calls/eight tool calls
within 90 seconds (20 seconds per provider call, no SDK retries). Duplicate tool execution is blocked.
An assistant lease prevents concurrent retries of the same request from submitting duplicate work.
LLM wording can still be wrong: inspect the attached evidence when a numerical claim matters.

## Browser account access

The new /app workspace validates Better Auth sessions and scopes metadata/artifacts to the
verified personal account. See [workspace guide](workspace.md) for the browser workflow.
The worker scans account workspaces; legacy .data records remain separate. The curl learning
examples below require explicit private CLI mode on a loopback API/worker:
`CI_AUTH_MODE=private pnpm dev:api` and `CI_AUTH_MODE=private pnpm worker:api`.
Do not run a private API alongside the authenticated app or expose it publicly.

## Supported journey

Start API and worker as described in the root README. The examples below use shell variables from
the preceding step. If token protection is enabled, add `-H "Authorization: Bearer $CI_API_TOKEN"`.
Use `/docs` to inspect all schemas, bounds and responses.

```sh
API=http://127.0.0.1:8000/api/v1
DATASET_ID=$(curl --fail --silent --show-error "$API/datasets/upload" \
  -F 'file=@/absolute/path/history.csv' | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
curl --fail --silent --show-error "$API/datasets/$DATASET_ID/profile" | python3 -m json.tool
curl --fail --silent --show-error -X POST "$API/datasets/$DATASET_ID/target-check" \
  -H 'Content-Type: application/json' -d '{"target_column":"Churn","positive_label":"Yes"}'
```

Confirm that each feature exists before the outcome and that the supplied label fits the real business
question. A checkbox records your assertion; it is not independent leakage verification.
The target and customer ID cannot be model inputs. The saved task is immutable; corrected choices
require a new task, and altered files require a new upload. New tasks are exploratory experiments,
not a way to regain an unbiased estimate after inspecting the same customers' test outcomes.

```sh
TASK_ID=$(curl --fail --silent --show-error -X POST "$API/datasets/$DATASET_ID/tasks" \
  -H 'Content-Type: application/json' -d '{
    "target_column":"Churn","positive_label":"Yes","id_column":"customerID",
    "feature_columns":["tenure","Contract","MonthlyCharges","TotalCharges"],
    "features_available_at_prediction":true
  }' | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
curl --fail --silent --show-error "$API/tasks/$TASK_ID/plan" | python3 -m json.tool
KEY=$(python3 -c 'from uuid import uuid4; print(uuid4())')
curl --fail --silent --show-error -X POST "$API/jobs/train" \
  -H 'Content-Type: application/json' \
  -d "{\"task_id\":\"$TASK_ID\",\"idempotency_key\":\"$KEY\",\"search_trials\":0,\"threshold\":0.5}"
```

Copy the returned job ID. Poll `GET /jobs/{job_id}`. `state=succeeded` plus `result_id` identifies
the saved run; other states are queued, running, failed or cancelled. No model call is needed to poll.
`POST /jobs/{job_id}/cancel` cancels queued work immediately or requests the worker to stop running work.
The default queue allows 20 pending/running jobs; execution defaults to a 600-second limit.

```sh
JOB_ID=copy-returned-job-id
curl --fail --silent --show-error "$API/jobs/$JOB_ID" | python3 -m json.tool
RUN_ID=copy-successful-result-id
curl --fail --silent --show-error "$API/runs/$RUN_ID" | python3 -m json.tool
```

The baseline predicts class prevalence. Logistic Regression models a binary label; linear regression
is for a continuous target and is not appropriate for this task. RF/XGBoost capture nonlinear effects.
Numeric columns are detected from training rows, imputed with training medians and scaled. Categories
use training-mode imputation and one-hot encoding; unknown values use the saved ignore-unknown rule.
All candidates use the same row assignments. Selection maximizes **validation average precision**;
accuracy, precision/recall/F1, ROC-AUC and confusion counts are also reported. Runtime, parameters,
failed candidates and warnings are visible. Up to eight additional fixed parameter variants can be
requested with `search_trials`; this is bounded holdout search, not nested cross-validation.

Choose the threshold in the training request before viewing final test results. Threshold tuning and
cross-validation are not automated. A contact count ranks customers independently of that threshold.
Final evaluation applies the selected train-fitted pipeline to held-out test rows once and caches it.
It freezes training/calibration for that task and blocks evaluating a different run of the same task.
The same run may be retried safely if publication was interrupted. Do any optional calibration first.

```sh
KEY=$(python3 -c 'from uuid import uuid4; print(uuid4())')
curl --fail --silent --show-error -X POST "$API/jobs/evaluate" \
  -H 'Content-Type: application/json' \
  -d "{\"run_id\":\"$RUN_ID\",\"idempotency_key\":\"$KEY\"}"
# After this job succeeds:
curl --fail --silent --show-error "$API/runs/$RUN_ID/evaluation" | python3 -m json.tool
```

Upload a separate current-customer sheet with the saved features and ID column. The target is optional;
if present, it is ignored. Missing features, duplicate/missing IDs and incompatible numeric values fail
the scoring job. Extra columns are ignored explicitly; unknown-category counts are reported.

```sh
SCORING_ID=$(curl --fail --silent --show-error "$API/datasets/upload" \
  -F 'file=@/absolute/path/current.csv' | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
KEY=$(python3 -c 'from uuid import uuid4; print(uuid4())')
curl --fail --silent --show-error -X POST "$API/jobs/score" \
  -H 'Content-Type: application/json' \
  -d "{\"run_id\":\"$RUN_ID\",\"dataset_id\":\"$SCORING_ID\",\"contact_count\":10,\"idempotency_key\":\"$KEY\"}"
SCORE_ID=copy-scoring-job-result-id
curl --fail --silent --show-error "$API/scores/$SCORE_ID/customers?limit=10" | python3 -m json.tool
curl --fail --silent --show-error "$API/scores/$SCORE_ID/export?top_k=10" -o shortlist.csv
curl --fail --silent --show-error "$API/runs/$RUN_ID/report" -o experiment.html
```

Every customer retains a one-based source row reference and ID. Ranking ties follow input order.
Exports include model/run and dataset references; potentially executable spreadsheet identifiers are
prefixed with an apostrophe. The manifest's contact count records the chosen budget; `top_k` controls
the exported list. Scoring data has no measured accuracy unless outcomes are evaluated separately.

## P1 options

Each compute operation returns 202 and follows the same job polling convention. Include a new UUID
`idempotency_key` with each request. All diagnostics are labeled validation/development or final test.

| Endpoint                                  | Additional payload                                                             | Result                                                                  |
| ----------------------------------------- | ------------------------------------------------------------------------------ | ----------------------------------------------------------------------- |
| `POST /jobs/diagnostics`                  | `run_id`, optional `segment_column`, `heuristic_column`, `heuristic_direction` | Analysis ID: importance, contact curve, reliability bins, segments/rule |
| `POST /jobs/calibrate`                    | `run_id` before final evaluation                                               | New calibrated run ID; original run retained                            |
| `POST /jobs/explain`                      | `score_id`, `row_reference`                                                    | Analysis ID: one-feature reference perturbations                        |
| `POST /jobs/leakage-demo`                 | `task_id`                                                                      | Analysis ID: validation comparison using a synthetic target-copy column |
| `POST /runs/compare`                      | `run_ids` (2–5 UUIDs)                                                          | Compatibility flags plus base-model validation results                  |
| `GET /analyses/{id}`                      | —                                                                              | Stored analysis with identity/provenance                                |
| `GET /runs?limit=25&offset=0`             | —                                                                              | Saved run history                                                       |
| `POST /datasets/upload?sheet_name=Sheet1` | `.xlsx` multipart file                                                         | Canonical CSV dataset, dates normalized to ISO                          |

Excel imports reject formulas, macros, invalid XML and oversized expanded archives. A multi-sheet
workbook requires an explicit sheet name. Original workbooks are converted into canonical CSV rather
than retained; the original filename is recorded. Blank rows are skipped and blank cells are missing.

Permutation importance measures validation AP reduction when shuffling an original feature (three
repetitions, at most 1,000 rows). Correlated features can share or hide importance. Customer explanations
replace one feature with a training median/mode and report the score change. This is **sensitivity,
not SHAP, an additive explanation or a causal effect**; the reference can be an unrealistic customer.
The synthetic leakage experiment never publishes a usable customer-scoring pipeline.

Contact curves report precision, recall and lift at 5/10/20/50/100% of labeled evaluation rows.
Segment analysis supports at most 20 groups; each requires 30 rows and five cases of each class to
report metrics, otherwise an insufficiency warning. Accuracy includes a Wilson 95% interval; this
does not establish fairness or account for repeated searching across segments. The heuristic is a
user-confirmed numeric feature ranked in the requested `higher_risk` or `lower_risk` direction.

Calibration uses a frozen base estimator and sigmoid fit on half the validation rows. The other half
provides Brier/reliability diagnostics. At least ten validation examples of each class are required.
This development data was already involved in base-model selection, so improvements are not unbiased
final performance claims. The original comparison remains the base-model leaderboard; calibration
metadata describes the changed pipeline. The final test supplies a separate calibration check.

For value-aware scoring add `value_column`, optional `value_unit`, and `ranking:"risk_x_value"`
to the score request. Values must be finite and nonnegative. Outputs contain both risk rank and
priority rank. Risk × value is an **exposure proxy**, not established expected loss or saved revenue.

## Assistant and evidence

`POST /assistant/messages` accepts `dataset_id`, a `question`, and `idempotency_key`; optionally include
matching `task_id`, `run_id`, `job_id`, `score_id`, `analysis_id` and `conversation_id`. Use the original
training dataset as the conversation context when inspecting a run's separate score set. Results
include answer, conversation/turn IDs, tool events with evidence paths, model call count and `trace_id`.
`GET /assistant/conversations/{id}` restores the first 100 saved turns; the agent uses the last four
turns as context. Scope and workflow restrictions are enforced in Python, independently of its prompt.

`allow_training:true` requires a confirmed `task_id` and explicitly authorizes the fixed four-candidate
plan at threshold 0.5. The agent must retrieve the plan before submission. It returns a queued job ID;
use the job API to observe completion. For custom search/threshold, use the explicit training API.
Read-only calls can inspect profiles, tasks, runs, jobs, score manifests and stored diagnostics. Other
compute operations use the explicit job APIs. Legacy `/assistant/inspect` and check scripts remain
available for the learning path.

Questions and aggregate evidence go to the configured provider; secrets and raw previews do not.
Chat text is user-supplied and stored locally: avoid pasting credentials or customer personal details.
Generated prose is not a validated numerical report. Tool evidence is the authoritative result.
Provider failures return a controlled 502; unavailable configuration returns 503. Retry the same
message key to retrieve an already successful response without another provider call.

## LLM gateway, tracing and evals (M1)

Every model call goes through `agent/llm.py` (`LLMGateway`). It retries only timeouts, connection
failures, 429 and 5xx responses (`CI_NEBIUS_MAX_RETRIES`, default 1, with backoff limited by the
turn's 180-second deadline). Typed actions (`structured`) get one repair attempt after a
validation failure; only the validation locations and messages are sent back, never the rejected values.
`NEBIUS_FAST_MODEL` is optional: when set, the fast model selects tools and the primary model
writes the final answer, at the cost of one extra call. Leaving it unset keeps the earlier single-model behavior.

Each AI operation saves an `AgentTrace` plus `AgentSpan` rows (model and tool calls, latency,
attempts, tokens, evidence paths, prompt version) in the account's own metadata database, including
failed operations. Prompts, evidence and answers are not copied into traces. Cost is reported only
for models priced in `CI_MODEL_PRICES`; otherwise it stays null. Read traces with
`GET /assistant/traces` and `GET /assistant/traces/{id}`. System prompts live in
`agent/prompts/<name>.v<N>.md` and are pinned in `ACTIVE`. Change one by adding a new version so
traces and eval reports stay comparable.

`POST /assistant/messages/stream` runs the same turn as `/messages` and returns server-sent events:
`model_start`/`model_end`, `tool_start`/`tool_end`, then `answer` (the full response) or `error`.
The turn completes even if the browser disconnects, and the Copilot page renders these steps live.

`pnpm eval:agent` replays recorded provider responses (`apps/api/evals/cassettes`) against a
seeded synthetic SaaS workspace and grades:

- tool trajectory
- numeric grounding (each non-trivial number must appear in a tool output or the question)
- required caveat language
- call budget
- schema validity

`pnpm eval:agent:live` calls Nebius, and `pnpm eval:agent:record` also refreshes the cassettes.
Both spend credits. Reports are written to `.data/evals/`. The baseline recorded on October 29,
2026 with `nvidia/Nemotron-3_5-Lightning` passed 4/7 scenarios with 0.94 mean numeric grounding.
The failures were invented thresholds in two answers and a self-computed "saved accounts" figure
next to the ROI tool output. Replays are free and deterministic but reflect the recorded model
output. Only live runs measure the current model.

## Investigations and answer verification (M2)

`POST /investigations` (or `/investigations/stream` for server-sent events) takes `run_id`, a
`question`, `provider_consent: true` and an `idempotency_key`. A LangGraph state graph
(`agent/graph/investigator.py`) then runs these steps:

1. **gather**: overview, single-feature association ranking (Cramér's V) and model summary.
2. **plan**: the model proposes up to 4 hypotheses as typed checks.
3. **analyze**: deterministic `segment_rates` or `compare_cohorts` analyses with Wilson and Newcombe
   95% intervals (`ml/investigation.py`).
4. **follow_up**: optionally, up to 2 more checks.
5. **write**: the model writes findings that cite evidence IDs.
6. **verify**: deterministic code checks the report (`agent/verification.py`).
7. **revise**: at most once.
8. **finalize**.

The checks reject identifiers, the target and any column that isn't an approved pre-outcome
feature. They only use development rows (train + validation); final test rows are never read.

The verifier withholds a finding when:

- it cites missing or failed evidence;
- any number in it is not in the cited evidence;
- it uses causal wording about churn.

Withheld statements stay visible with their reasons. The report is saved as an analysis with
`kind: investigation`, together with its plan, all evidence, the draft, the verification result
and its trace ID. Plan and the first draft are required steps. A failed follow-up or revision is
skipped instead of failing the run. The run is limited to 8 model calls and 180 seconds.

Chat answers get the same checks. Every number must appear in a tool output or the question,
and causal wording about churn is flagged. One revision is requested, and anything that still
fails is returned in `verification` rather than edited by code. A bad _value_ in an action's
arguments, an action that refuses (for example, a schema review that fails validation), or a
repeated read is now returned to the model as a tool error it can correct. Unknown tools,
out-of-scope IDs, server-owned or unknown fields, and duplicates within one batch remain fatal.

Live evals on October 29, 2026 (`nvidia/Nemotron-3_5-Lightning`, assistant prompt v2, 3 samples per
scenario) gave the results below. These are small samples, so treat them as indicative.

| Scenario          | Passed |
| ----------------- | ------ |
| task_review       | 3/3    |
| model_selection   | 3/3    |
| dataset_readiness | 2/3    |
| leakage_probe     | 2/3    |
| causal_overclaim  | 1/3    |
| contact_budget    | 1/3    |

Mean numeric grounding was 0.98, up from 0.94 with prompt v1 and no checks. Both investigation
scenarios passed: they recovered all three planted drivers and correctly found no plan-tier effect.
The remaining failures are:

- a missing explicit causation caveat;
- the call budget running out on budget questions;
- one out-of-scope tool request.

## Data lifecycle and failures

`GET /datasets`, `/datasets/{id}`, `/tasks`, `/jobs`, `/runs` recover the local workspace.
`DELETE /datasets/{id}` refuses dependent artifacts; `?cascade=true` deletes the dataset, its tasks,
runs, related scores/analyses, dependent job history and conversations after active work has stopped.
Related queued/running jobs and active assistant leases block deletion. Files are moved to temporary
trash before the database commit, with rollback restoration on routine failure. This is not a
cross-filesystem transaction or a power-loss guarantee: back up `.data` before important work and
do not run deletion concurrently with independent CLI training scripts.

Errors use `code`, `message`, and request ID when available. 400 means incompatible workflow/input;
404 missing resource; 409 conflict/corrupt or incompatible saved artifact; 413 upload budget;
422 invalid field contract; 429 queue full; 502/503 provider failure/unconfigured. Worker failures
appear in the job record; queued jobs will remain queued while the worker is stopped.
After cancellation/interruption, a hidden staging directory or an unreferenced completed artifact
can remain if a process stops during publication. These are never listed as successful jobs. Retain
only application-owned artifacts and clean leftovers manually after stopping all writers/backing up.

Pipeline loading verifies checksums, versions, preprocessing source and feature schema before loading
application-created joblib files. No arbitrary uploaded pickle is accepted. Saved pipelines are tied
to their recorded environment; dependency or preprocessing changes may require retraining.

## Next product milestone

Build real frontend screens against these contracts: upload/profile → task confirmation → plan/job
progress → separate validation/test results → scoring/contact budget/export → evidence chat. Use
React Query for status polling; keep long-job polling outside the LLM. Add privacy notice before the
first assistant call. Do not show fabricated model metrics or a claim of future churn without dated
labels. Public hosting requires real identity/tenancy, rate limits and a deployment plan beyond this
private local backend. Time/group evaluation and other target types remain P2/explicit new work.

## Verification of this backend pass

- 32 isolated pytest cases passed, covering real CPU training, worker subprocess execution,
  persistence, calibration, final test freezing, scoring/export, diagnostics, deletion,
  queue concurrency/recovery, cancellation/timeout control and agent tool boundaries.
- Ruff and mypy pass; the documented pnpm backend commands were exercised using installed Node 22.
- A separate temporary Uvicorn API and worker completed the synthetic HTTP demo, including a
  calibrated pipeline, 90 held-out test rows and a five-customer shortlist. A second worker was
  refused by the data-directory lock. No provider calls or user customer data were used.
- The existing saved Telco run's manifest/checksums/environment and pipeline reload passed.
  Its test partition remains unevaluated by this pass.

This evidence establishes the tested local workflow, not a guarantee of no bugs or production scale.
A fresh live Nebius tool-calling smoke test is still needed against the account's currently available
model; `demo.py --with-agent` is the explicit opt-in path. Existing earlier Nebius checks proved
connectivity but do not replace testing the new conversation workflow.

## Workspace memory and approvals (M2, October 29)

- `GET/PUT /api/v1/memory` stores confirmed business assumptions (budget, contact and offer
  cost, save rate, retained value, currency) and up to 20 decisions per workspace (`WorkspaceFact`).
  `POST /retention/roi` remembers the assumptions a person entered (`source=budget_planner`).
  These are assumptions, never measured outcomes.
- `GET /api/v1/actions` and `POST /actions/{id}/approve|reject` manage `PendingAction` records.
  With `workspace_tools=true` and no `allow_training`, the assistant gets
  `request_training_approval`, which creates a pending action; approving it queues the default
  training job with an idempotency key derived from the action ID.
- With `workspace_tools=true` the assistant also gets `read_workspace_memory`,
  `list_workspace_resources` (an owner-scoped catalogue) and, with a scoring batch, `find_accounts`.
  The flag defaults to false so recorded eval cassettes still replay.
- The assistant prompt is `assistant.v3`. Tests: `tests/test_workspace.py`.

## Account data sources and time-ordered evaluation (M3, October 29)

- **Sources** (`/api/v1/sources`) are folders of normalised tables under `<workspace>/sources/<id>`:
  `accounts` (account_id, created_at, optional cancelled_at, plan, seats, billing_cycle, industry,
  region), `invoices` (account_id, date, amount, status), `usage` (account_id, date, active_users,
  optional logins) and `tickets` (account_id, created_at, optional subject/body). Create one from a
  CSV bundle (`POST /sources/upload`, multipart) or the labelled generator (`POST /sources/synthetic`,
  900 synthetic accounts with planted drivers: usage decline, failed payments, cancel-intent and bug
  tickets, monthly billing, few seats).
- **Snapshots** (`ml/snapshots.py`): `POST /sources/{id}/datasets {horizon_days, purpose}` builds
  month-end snapshots. Every feature uses only events on or before the snapshot date; the label is
  `churned_within_{N}d`; dates whose horizon has not fully elapsed are dropped and counted. The
  result is saved as an ordinary dataset, so training, scoring, investigations and the assistant
  are reused. `purpose=scoring` builds features for accounts active at the end of the data.
- **Ticket topics** use a fixed keyword taxonomy (billing, bug, onboarding, cancel intent,
  performance): no fitting, so no leakage across time.
- **Time-ordered evaluation**: tasks accept `time_column`; `evaluation_strategy` becomes
  `time_ordered` and `ml/splitting.make_time_partitions` puts the oldest ~70% of rows in training,
  the next ~15% in validation and the newest ~15% in the reserved test, never splitting a date.
  Training-row CV remains stratified within the training period.
- **Schema migration**: `core/database.add_missing_columns` adds new nullable columns to existing
  workspace databases (here `task.time_column`). Split and run fingerprints omit `time_column` while
  it is unset, so splits and runs saved earlier still validate.
- `GET /sources/{id}/accounts/{account_id}` returns an account timeline (usage, invoices, tickets).
- Tests: `tests/test_sources.py` (point-in-time correctness, unobserved horizons, end-to-end
  synthetic source → time-ordered training, bundle validation).

## Read-only connectors (M3, October 29)

- `GET/POST /api/v1/connections`, `POST /connections/{id}/sync`, `DELETE /connections/{id}`.
  Providers: `stripe` (customers, subscriptions, invoices) and `hubspot` (companies, tickets with
  company associations; an optional `churn_date` company property supplies labels).
- Connectors are disabled until `CI_CREDENTIALS_KEY` (a Fernet key) is set. A credential is
  verified with one read, then stored only as ciphertext in the workspace database. It is never
  returned, logged or written into a source. Syncs only issue GET requests, stop after 100 pages
  per object, and save a new source (`kind=stripe|hubspot`) that feeds the same snapshot builder.
- Stripe mapping: an account is cancelled when all its subscriptions have ended (latest
  `ended_at`); annual prices become `billing_cycle=annual`; paid invoices and open or
  uncollectible invoices with payment attempts (as `failed`) are kept; drafts and voids are skipped.
- Tests: `tests/test_connectors.py` (mocked HTTP; checks the secret never appears in responses,
  storage or source files, and that bad credentials are rejected).

### Stripe as a live daily feed (October 30)

- `pnpm setup:connectors` writes `CI_CREDENTIALS_KEY` to `apps/api/.env` once and never prints
  it. An existing key is kept: changing it makes saved connections unreadable. Restart the API
  and worker afterwards.
- The Data sources page connects Stripe with a **restricted read-only key** (Read on Customers,
  Subscriptions, Invoices). Anyone in the workspace sees connection status; only owners and
  admins connect, sync or disconnect (`core/permissions.py`).
- Provider requests retry 429/5xx and network errors up to 3 attempts, waiting `Retry-After`
  capped at 5 s. A 403 names the object the key can't read ("This key can't read
  subscriptions"). `GET /connections` adds `last_counts` from the latest synced source.
- Stripe gives billing signals only. `build_dataset` now leaves out constant features (for
  example the all-zero ticket counts of a Stripe-only source), which task validation rejects.
- Daily use: train from the synced source (Data sources → Train from this data), make that run
  active, then pick the connection in Results → Automatic check. `PUT /schedule` refuses a
  connection or source the active model can't score ("trained on different data", listing the
  missing features). Deleting a connection pauses a schedule that used it.
- Tests: `tests/test_stripe_loop.py` runs connect → sync (with a retried 503) → train → promote
  → schedule → cycle → digest against a fake paged Stripe API built from the labelled synthetic
  generator, plus the model-mismatch refusal and the missing-permission error. No live Stripe
  account was used.

### HubSpot, alone or matched with Stripe (October 30)

- Connect with a HubSpot **private app token** (Development → Legacy apps → Private). Scopes:
  `crm.objects.companies.read`, `crm.schemas.companies.read` (to list date properties) and
  `tickets`; task write-back also needs a task write scope. A missing scope surfaces as a clear
  "can't read …" or "refused task creation" error.
- HubSpot has no standard churn field. `GET /connections/{id}/properties` (admin only) lists
  company date properties; `PUT /connections/{id}/settings {"churn_property": …}` stores the one
  an admin picks, validated against that list. Without it no company is marked cancelled, so the
  data can be scored but not trained on. The old hard-coded `churn_date` is gone.
- `PUT /connections/{stripe_id}/settings {"enrich_connection_id": hubspot_id}` matches each Stripe
  customer's email domain to a HubSpot company `domain` on every Stripe sync. The source is
  `kind=stripe+hubspot`: Stripe stays the record of cancellation; matched customers gain
  `industry` and their company's tickets. Personal mailboxes (gmail.com and similar) and domains
  claimed by more than one company never match. The manifest's `match` holds matched / total /
  rate / ambiguous domains, shown on the Stripe card.
- Domains and emails are used in memory only and never written to source files. The Stripe →
  HubSpot company links are saved as `links.json` beside the source (not a model feature) so
  approved plays on Stripe-anchored accounts create tasks on the matched companies.
- Deleting a HubSpot connection unlinks Stripe connections that used it.
- Tests: `tests/test_hubspot_loop.py` (fake paged HubSpot API from the synthetic generator: churn
  property choice, domain match with personal mailboxes and an ambiguous domain, no domains on
  disk, ticket features in training, task write-back through the links, unlinking). No live
  HubSpot account was used.

### Indian billing and CRM: Razorpay, Zoho Billing, Zoho CRM (October 30)

Stripe only takes new Indian businesses by invitation (since May 2024), so Indian clients connect
Razorpay or Zoho Billing for billing and Zoho CRM as the CRM.

- **Roles.** `connectors.REGISTRY` names each provider's role: billing (stripe, razorpay,
  zoho_billing) owns cancellations; CRM (hubspot, zoho_crm) adds industry and tickets, a churn
  field and task write-back. Any billing connection can match with any CRM; the source kind is
  `<billing>+<crm>`. Match stats are `billing_accounts`, `matched`, `matched_by_crm_id`, `rate`.
- **Credentials.** `POST /connections` takes `secret` (Stripe, HubSpot) or `fields` (Razorpay:
  `key_id`, `key_secret`; Zoho: `region`, `client_id`, `client_secret`, `code`, optional
  `organization_id`). Multi-field credentials are stored as encrypted JSON.
- **Razorpay** (`services/razorpay.py`): HTTP basic auth; customers, subscriptions, plans and
  invoices paged by `count`/`skip`; amounts in paise ÷ 100. Cancelled when every subscription is
  cancelled/completed/expired; expired or overdue invoices and halted subscriptions are failed
  payments; yearly plans are annual. Razorpay keys can't be read-only.
- **Zoho** (`services/zoho.py`): Self Client. The one-time code is exchanged once for a refresh
  token (never stored as a code); each sync refreshes a one-hour access token in memory. Region
  picks the accounts server (in, com, eu, au, jp, ca, sa); the token's `api_domain` must be a
  zohoapis host. Zoho reports bad codes as HTTP 200 with `error`, mapped to plain messages.
  - **Zoho CRM:** `/crm/v8/Accounts` (200 per page, `page_token` past 2,000), Cases as tickets
    (if unreadable the sync continues with a note), date fields from
    `/crm/v8/settings/fields?module=Accounts`, and Tasks (`What_Id`, `$se_module: Accounts`,
    batches of 100) for approved plays.
  - **Zoho Billing:** `/billing/v1/{customers,subscriptions,invoices}` with the
    `X-com-zoho-subscriptions-organizationid` header; with several organisations the admin
    enters one ID. Customers carrying `zcrm_account_id` match the CRM by that ID before domain;
    it is never saved to source files.
- **Task targets are only real CRM records:** a matched billing account, or an ID from the CRM's
  own latest sync. A numeric billing ID is never assumed to be a CRM ID.
- A Zoho 204 is an empty page; a 401 with a SCOPE code reads as a missing permission.
- Tests: `tests/test_razorpay_loop.py` (fake paged Razorpay from the synthetic generator, full
  daily loop, status mapping) and `tests/test_zoho_loop.py` (fake Zoho accounts/CRM/Billing:
  code exchange, secrets never stored or returned, paging past 2,000 accounts, Cases fallback,
  organisation choice, CRM-ID-first matching, tasks). Field names and statuses follow the
  providers' documentation; no live Razorpay or Zoho account was used yet.
- In development the account backend accepts both `http://localhost:5173` and
  `http://127.0.0.1:5173` (`allowedOrigins`); production accepts exactly `APP_ORIGIN`.

### Email digest (October 30)

- Set `CI_RESEND_API_KEY` and `CI_EMAIL_FROM` (an address on a domain verified in Resend) in
  `apps/api/.env`; without both, email stays off and the Settings card says so.
- `GET/PUT /api/v1/email/subscription` turns the digest on or off **for the requester only**.
  In account mode the address is the signed-in account's own (the identity bridge now passes
  `email`); only private CLI mode accepts a typed address. Viewers may manage their own
  digest. At most 50 recipients per workspace; addresses are shown masked.
- After each scheduled check, `notify()` emails each recipient separately (Resend
  `Idempotency-Key` = digest item + user), then records `emailed_at` and `emailed` on the
  digest item so a retry never sends twice. A delivery failure is recorded, never raised.
- Content: the digest title and aggregate lines, the verified brief's call-first reasons
  (pseudonymous, by position) and recommended play, links into the app, and a
  `List-Unsubscribe` link to Settings. "Review first" lines, customer IDs and rows are never
  included; every dynamic string is HTML-escaped.
- `POST /api/v1/email/test` sends a sample to your own subscribed address, at most once a minute,
  and explains a refusal (unverified sender domain or invalid key).
- Tests: `tests/test_email.py` (mocked Resend). No real email was sent.

## Playbook search with citations (M3, October 29)

`POST /api/v1/playbooks` (multipart `file`, optional `title`) stores a Markdown or text playbook
(UTF-8, up to 1 MB, at most 50 per workspace) under `.data/playbooks/{id}`. It is split into
heading-aware passages of at most 900 characters. `GET /api/v1/playbooks/search?q=` ranks passages
with BM25. This is deterministic keyword retrieval with no provider call; embedding retrieval is
still planned. Each result has a citation ID (`P1`…) and an evidence path
`/api/v1/playbooks/{id}#passage-{n}`.

When the workspace has playbooks and `workspace_tools` is on, the assistant gets
`search_playbooks(resource_id, query)`. This is the only tool with a free-text argument. It allows
at most three searches per answer. Assistant prompt v4 tells the model to cite passages as `[P1]`,
to treat playbooks as intended practice rather than measured results, and to say when they don't
cover a question. Passage text is untrusted data like every other tool output.

## Monitoring, scheduler and autonomy (M4, October 29)

- **Active model:** `GET /registry`, `POST /registry/promote {run_id}` and
  `POST /registry/rollback`. Promotion loads the pipeline first, so runs that can no longer score
  (for example, after a preprocessing change) are refused.
- **Drift:** `POST /monitoring/drift?score_id=` computes PSI for every model input, comparing the
  run's training rows with the scored population.
  - For time-ordered models, the reference is the newest training snapshot date only, because
    older snapshots differ by design (for example, tenure grows).
  - It also reports the risk-score PSI against the previous batch from the same run.
  - Bands: < 0.1 stable, 0.1–0.25 watch, > 0.25 alert. These are a rule of thumb, not a test.
- **Realized performance:** measured only from known outcomes, either with
  `POST /monitoring/performance` (an outcomes dataset joined on customer ID) or, inside a cycle,
  from a newer sync of the same source once a batch's horizon has fully elapsed. Batches whose
  outcomes aren't known yet are refused.
- **Schedule:** `GET/PUT /schedule` chooses a connector (synced each time) or a saved source,
  cadence, horizon and contact count. `POST /schedule/run` queues a cycle now.
  - Every 30 s, the worker checks each workspace and queues a due cycle as an ordinary idempotent
    `cycle` job (key = the scheduled slot).
  - A cycle never trains automatically and never contacts anyone.
- **Current snapshots for scoring** are now taken at the last date both usage and invoices cover,
  not at the latest date in any table. An invoice dated after the last usage export made every
  account look inactive; this was found by the drift check.
- **Autonomy:** `GET/PUT /autonomy`.
  - `observe` writes the digest.
  - `recommend` also lists the top accounts and a related playbook passage.
  - `act_with_approval` also creates a `retrain` pending action on an alert. Approving it rebuilds
    snapshots from the source, recreates the active model's churn definition on them and queues
    training.
  - Guardrails are enforced in code:
    - `paused` (the kill switch) blocks every traced AI operation, cycles and new proposals;
    - `daily_token_budget` is checked against today's traced tokens before any AI operation;
    - `daily_action_quota` limits pending actions per 24 hours.
- **Digest:** `GET /digest` and `POST /digest/{id}/read`. Each entry links to its scores and
  reports, and failed cycles are recorded too.
  - An optional Slack incoming webhook (`slack_webhook_url` on `PUT /autonomy`; empty string
    disconnects) is stored Fernet-encrypted with `CI_CREDENTIALS_KEY`, and is never returned.
  - Slack receives the title, the aggregate lines and links, but no account IDs.

## Holdouts, measured lift and plays (M5, October 30)

- **Holdouts:** `holdout_rate` on scoring (0–0.5; the UI offers 20%) marks a seeded random
  subset of the contact list as `group: "holdout"`.
  - The seed comes from the idempotency key, so a retried request holds out the same accounts.
  - Contact exports, outreach drafts, digest suggestions and plays never include holdout
    accounts.
  - Batches scored before this change have no groups.
- **Lift:** `POST /monitoring/lift` (an outcomes file joined on ID, with an optional segment
  column) or `POST /monitoring/lift/source` (a later sync of the same source once the horizon has
  elapsed) writes a `lift` report. Scheduled checks also measure lift for earlier batches that
  had a holdout.
  - The report gives contact versus holdout churn rates and the difference with a 95%
    percentile bootstrap interval (2,000 resamples, fixed seed).
  - The verdict is `fewer_churned` or `more_churned` only when the interval excludes zero.
  - Lift needs at least 10 accounts with outcomes in each group.
  - It is intention-to-treat: it measures being on the contact list, not confirmed contact.
- **Plays:** `POST /actions/plays {score_id, title, instructions, accounts ≤ 200,
connection_id?}` creates a pending `play` action, counted against the daily proposal quota.
  - Approval through a HubSpot connection with `write_enabled` (`PUT /connections/{id}/write`
    with `confirm: true`) creates one task per account whose ID is a HubSpot company ID; other
    IDs are counted as skipped.
  - Otherwise approval leaves the list ready at `GET /actions/{id}/export` (CSV, with spreadsheet
    formulas escaped).
  - Nothing ever contacts customers.
- **Assistant prompt v5** says that outreach effect is measured only by the holdout comparison,
  and that holdout accounts are never suggested for contact.

## Governance (M6, October 30)

- **Roles:** `GET /workspace/identity` returns the caller's role. The rules are in
  `core/permissions.py` (see docs/auth.md).
- **Audit log:** every successful non-GET API request is recorded with method, path, actor, role
  and status; request bodies are never stored. Automated actions are recorded as
  `system:<component>`. `GET /audit` is for owners and admins.
- **Usage:** `GET /usage?month=YYYY-MM` returns AI operations and tokens, cost (only when
  `CI_MODEL_PRICES` is set), jobs by kind and accounts scored.
- **Privacy:** `GET/PUT /privacy` takes `blocked_columns` and `default_patterns`. Withheld columns
  still train models on the server, but:
  - profiles sent to the AI drop their statistics;
  - investigations skip them;
  - outreach personalisation refuses them.
- **Retention:** `GET/PUT /retention-policy {days ≥ 7}` and `POST /retention-policy/apply`. The
  worker also applies the policy once a day. It deletes old scores, analyses, conversations,
  traces, monitoring reports, digest items and unused uploads. It keeps models, the datasets
  that tasks depend on, and the audit log.

## Nemotron briefs and account reasons (October 30)

- **Reasons:** `GET /scores/{id}/reasons` computes drivers for the top 15 contact-list accounts
  (holdout excluded) and caches them in `scores/{id}/reasons.json`.
  - Method: swap one input for its typical training value (median or most common), re-score, and
    keep the inputs whose swap lowers the score most. These are associations, not causes.
- **Notes:** `POST /scores/{id}/reasons/notes {provider_consent: true}` asks Nemotron (prompt
  `account_notes`) for one short note per account.
- **Brief:** `POST /briefs {score_id, provider_consent: true}` asks Nemotron (prompt
  `daily_brief`) for a headline, what changed, up to 5 accounts to call first, a recommended play
  and caveats.
  - Reads: `GET /briefs/latest` and `GET /briefs/{id}`.
  - With the workspace setting `ai_briefs` on (admins only, `PUT /autonomy`), every scheduled
    check also writes a brief and notes.
  - A provider failure, kill switch or used-up budget leaves the check's measured results in place;
    the digest says why the brief is missing and a failed brief is recorded.
- **Privacy:**
  - Accounts reach the provider only as labels (A1…), and the server maps them back.
  - Evidence is pre-written in plain language (readable input names; shifts described as
    "changed a lot" or "changed somewhat") so internal fields never reach the text.
- **Verification** happens in code before anything is saved. Each sentence:
  - must use only numbers present in the evidence;
  - may contain no causal verb (any "drive", "cause", "lead to" or "due to", stricter than the
    investigation rule);
  - may contain no underscored field name;
  - if it's a "what changed" point, must name an input that actually changed (or the median risk).

  Failing items are withheld and listed in `verification.withheld`. Failing notes fall back to
  text computed from the drivers. A stringified nested object from the provider is parsed and then
  validated with the same strict schema.

- **Live check (October 30)** on the synthetic workspace with `nvidia/Nemotron-3_5-Lightning`:
  - 15 of 15 notes passed;
  - a brief with 13 to 24 numbers checked had 1 to 4 items withheld per run;
  - earlier attempts surfaced (and the gates caught) a stringified play object, internal jargon
    and an invented change.
  - verbatim items the verifier withheld in those runs: `what changed: unsupported numbers:
0.275`, `caveat: causal wording`, `headline: unsupported numbers: 20` (replaced by a computed
    headline) and `what changed: not about a measured change`.
  - The marketing site's model comparison uses the validation average precision from the
    synthetic demo run of October 29, 2026 (run `628d54df`): baseline 0.078, logistic regression
    0.117, random forest 0.168, XGBoost 0.172.
- **Not built yet:** Nemotron reading support-ticket text inside the model. It needs its own
  privacy design.

## Upload limits and large datasets (October 30)

Limits are settings, not constants:

| Setting                     | Default        | Covers                                                |
| --------------------------- | -------------- | ----------------------------------------------------- |
| `CI_MAX_UPLOAD_MB`          | 200            | CSV upload size, and each table in a source bundle    |
| `CI_MAX_ROWS`               | 1,000,000      | rows per dataset or bundle table                      |
| `CI_MAX_COLUMNS`            | 500            | columns per dataset                                   |
| `CI_MAX_EXCEL_MB`           | 50             | Excel uploads (openpyxl holds the workbook in memory) |
| `CI_WORKER_TIMEOUT_SECONDS` | 1800 (max 4 h) | the time budget for one job                           |

`/api/v1/capabilities` reports them, and the web app reads them from there.

- **Uploads** stream to a temporary file in 1 MB chunks and are validated row by row, so memory
  stays flat: 1,000,000 rows (34 MB) uploaded in about 4 s with no visible memory growth.
- **Request size:** the request-size middleware streams instead of buffering and limits per path.
  Uploads get the upload limit (bundles four times it); every other request gets 2 MB. This also
  fixes source bundles, which were silently capped at 11 MiB before.
- **Stored files** are no longer re-checked against today's limits, so lowering a limit never
  breaks existing datasets or models.
- **Faster loading:** the dataset loader now uses pandas' C parser with every cell as text, plus
  vectorised blank detection. A test confirms it returns exactly what the previous row-by-row
  reader did, and it falls back to that reader whenever shapes or headers disagree.
- **Profiling speed:** a 1M-row profile went from 59 s to 13 s. Profiles are not cached yet, so
  each view re-reads the file.
- **Scoring files** (`rows.json`) scale with the row limit, about 400 bytes per row.
