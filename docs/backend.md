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
include answer, conversation/turn IDs, tool events with evidence paths, and model call count.
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
