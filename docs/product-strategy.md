# Product strategy: autonomous retention agents for B2B SaaS

Approved October 29, 2026. Everything below is **planned** unless docs/backend.md, docs/workspace.md or
docs/retention-studio.md describe it as implemented. Milestones are built one at a time; each after M1
needs a separate go-ahead.

## Context

The existing product has a solid ML core: four model families, leakage guards, a reserved final test set,
calibration, contact policies, budget/ROI scenarios and per-user account isolation. The AI layer is thin.
It is a single hand-written OpenAI-SDK tool loop (`agent/workflow.py`) that reads computed results and
summarizes them, plus single-shot structured calls (`agent/provider.py::structured`) for briefings and
drafts. Exploration found:

- LangGraph and LangChain are installed but never imported.
- There are no evals, no tracing or token/cost accounting, no streaming, and memory is just the last 4 Q/A pairs.
- Each tool can run once per turn, and the agent can't discover resources beyond the IDs in the request.
- Two separate loops and two client setups exist (`inspection.py` + `services/assistant.py` with a hardcoded 20 s timeout).
- Data is one static CSV per task, split randomly, with no time horizon. B2B SaaS churn is account-level and
  time-based, so a random split leaks in that setting.
- There are no connectors, monitoring, scheduling, organisations/roles or outcome tracking.

Decisions so far: product first, no deadline; first buyer is B2B SaaS customer-success/revenue teams;
the main emphasis is **autonomous agents**; compute is unknown, so plan API-only and keep GPU work optional.

**Product thesis.** Move from "chat about my churn model" to an **AI retention analyst that runs every day**.
It watches account health and investigates why risk changed. It proposes cited, approval-gated actions
and later measures whether those actions worked. Customers pay for the loop of detect → explain → act →
measure, not for a chatbot.

The integrity rules in AGENTS.md still hold throughout:

- No generated Python or shell runs.
- Numbers come from tools.
- Approval comes before any outward action.
- Uplift is claimed only from holdout evidence.
- `ml/preprocessing.py` stays untouched, and legacy pipelines are kept.

## Roadmap: six milestones, built one at a time

### M1: AI engineering foundation (implemented October 29, 2026; see docs/backend.md)

1. **One LLM gateway** at `agent/llm.py`, replacing `provider_client`, the duplicate in `services/assistant.py` and parts of `structured()`.
   - Bounded retries with backoff and one repair retry for invalid structured output.
   - Model routing: a fast model for routing/tool selection, a strong model for synthesis. Check current Nebius model IDs before coding.
   - Reads `response.usage` to record tokens, latency and cost per call.
2. **Tracing.** Add `models/trace.py` (Trace and Span tables, owner-scoped) recording each model call, tool call, arguments hash, duration and tokens. Show a trace viewer in the Copilot UI, plus an optional OpenTelemetry export.
3. **Prompt registry.** Move prompts to versioned files in `agent/prompts/`, and store the prompt version on every trace.
4. **Eval harness** in `apps/api/evals/`, run as a new `pnpm eval:agent` script.
   - Scenarios: the telco benchmark (`docs/telco-validation-benchmark.json`) plus a synthetic SaaS dataset.
   - Deterministic graders:
     - Numeric-claim grounding: every number in the answer must appear in a tool output.
     - Tool-trajectory checks.
     - Leakage-refusal checks.
     - Schema validity.
   - An optional LLM judge for narrative quality.
   - Two modes: recorded (cassettes, free, runs in CI) and live (explicit flag, spends credits).
   - This is what turns the project from "uses an LLM" into AI engineering.
5. **Streaming.** Add an SSE endpoint for agent turns: action events, tool progress and the final answer. Update `workspace/pages/Copilot.tsx` to show steps live.

Not shipped from the M1 list:

- **OpenTelemetry export.** Traces can be read through the API, and the tracer's listener hook is where an exporter would attach.
- **Telco scenarios.** The telco benchmark file holds metrics only, with no customer rows, so the evals use a seeded synthetic SaaS dataset instead.

### M2: multi-agent retention investigator on LangGraph (the centerpiece; partly implemented October 29, 2026)

Implemented: the investigator graph (plan, deterministic analyses, follow-up, write, verify, revise),
the typed analysis tools, a deterministic verifier shared with chat answers, recoverable tool
errors, the Investigate page, and investigation evals with planted drivers. See docs/backend.md.
Also implemented (October 29): workspace memory (saved business assumptions and decisions,
pre-filling the budget planner and readable by the assistant), an approval Inbox (the assistant
creates pending training requests; a person approves before a job is queued), discovery tools
(`list_workspace_resources`, `find_accounts`), per-tool descriptions and assistant prompt v3.
The app enables these through `workspace_tools`; recorded evals keep them off so cassettes still
replay. Still planned: SHAP attributions and conversation ownership (with M6 organisations).

- Replace the linear loop with a **LangGraph state graph** at `agent/graph/`, checkpointed in SQLite.
- Graph nodes:
  - **Planner** turns the question into a list of hypotheses.
  - **Analyst** runs **typed analysis tools**. These are a constrained DSL run deterministically with pandas/DuckDB, never generated code:
    - compare cohorts
    - segment drill-down
    - trend over time
    - feature attribution
    - top movers
  - **Verifier/critic** pulls out every numeric or causal claim and checks it against tool outputs. Anything unsupported loops back or gets removed. Correlation-as-causation wording is rewritten.
  - **Writer** produces structured findings, each with evidence references.
- **Tool registry rewrite.** Give tools real descriptions and add owner-scoped discovery tools (`list_runs`, `list_scores`, `find_accounts`) so the agent can explore within the user's workspace. Keep server-side budgets, ownership checks and per-step limits, and replace "once per turn" with per-tool quotas.
- **Human-in-the-loop.** Use LangGraph `interrupt` before any action that costs money or changes state (training, campaign drafts, later CRM writes). Show approve/reject cards in the UI.
- **Memory.** Keep a per-workspace store of confirmed facts: the target definition, the user's business assumptions (save rate, contact cost) and decisions made. Summarize the conversation instead of keeping the last 4 turns. Add an owner field to `Conversation`.
- **Per-account explanations.** Add SHAP (TreeExplainer for RF/XGBoost) alongside the current perturbation sensitivity, which gives each account brief proper per-feature attributions.
- **Evals.** Extend the M1 suite with investigation scenarios that have known planted causes in synthetic data, and measure how often the agent recovers them.

### M3: B2B SaaS data layer (required before selling)

Implemented October 29: multi-table sources (CSV bundle and a labelled synthetic generator),
point-in-time snapshots with a prediction horizon, time-ordered evaluation, keyword ticket topics
account timelines, read-only Stripe/HubSpot connectors with encrypted credentials, and playbook
search with citations (lexical BM25 over the workspace's own Markdown/text playbooks; see
docs/backend.md). Still planned: embedding-based ticket topics and embedding retrieval, which need a
verified Nebius embedding model.

- **Account-level, multi-table model.** Accounts, subscriptions/invoices, product usage events and support tickets are joined into **point-in-time feature snapshots** with an explicit prediction horizon (for example, renewal within 90 days).
- **Time-based splits** that respect snapshot dates, added as a new split strategy next to the random split (old runs are kept).
- **Read-only connectors:** Stripe (subscriptions, MRR, failed payments) and HubSpot (companies, deals, tickets), with CSV staying as a fallback.
  - Credentials are stored server-side and encrypted.
  - The synthetic demo connector is labelled clearly as synthetic.
- **Unstructured signals.** Embed support-ticket text (Nebius embedding model) for topic/sentiment features and for retrieval in account briefs.
- **RAG over the customer's own CS playbooks.** Uploaded docs are chunked and embedded so recommendations cite playbook passages. This was a P2 item ("policy retrieval with citations").

### M4: autonomous operations (what makes it "autonomous")

Nemotron as the analyst (October 30): a checked daily brief after each scheduled check and
checked per-account notes on the at-risk list. See docs/backend.md.

Implemented October 29: active-model registry with promote/rollback, a scheduler in the existing
worker, scheduled cycles (sync → score with the active model → PSI drift and score shift → realized
performance once horizons elapse → digest), an in-app digest with an optional Slack webhook,
autonomy levels, a kill switch, a daily token budget and a daily proposal quota, and retraining
proposals that need approval. The cycle does not run an LLM investigation of changes; the digest
links to the evidence instead. Email digests are not implemented.

- **Scheduler** added to the existing worker (no new queue). It runs per-workspace jobs: daily sync → re-score with the **active model** → drift check → agent investigation of material changes → digest.
- **Model registry.** Add an active-model concept with promotion/rollback, plus retraining proposals that need approval.
- **Monitoring:**
  - feature drift (PSI)
  - score-distribution shift
  - realized performance once outcomes arrive (e.g. after the renewal date passes)
- **Daily/weekly digest.** In-app plus Slack/email notifications, each item linked to its trace and evidence.
- **Autonomy levels** set per workspace: observe → recommend → act-with-approval. Guardrails include a daily LLM budget, an action quota and a kill switch.

### M5: closed loop and proof of value (the selling point)

Implemented October 30:

- seeded holdout groups among each contact list (kept out of exports, drafts and "review first"
  lists);
- measured lift (contact versus holdout churn, 95% bootstrap interval, by segment when groups are
  large enough), from an outcomes file, a later source sync, or automatically in scheduled checks;
- plays queued for approval, delivered as HubSpot tasks (only through a connection the user
  explicitly opened for writing) or as a CSV export.
  Monitoring alerts can lead to approved retraining.

- **Approved actions write back** as HubSpot tasks or notes assigned to the account owner. Nothing is sent to end customers automatically.
- **Holdout control groups.** Assign a random holdout among flagged accounts. Track renewal and churn outcomes and report **measured retention lift with confidence intervals**. This is the only honest basis for an ROI claim.
- **Learning loop.** Outcomes feed retraining, and playbook effectiveness is reported by segment.

### M6: commercial readiness

Implemented October 30 (no deployment): organisation workspaces with owner/admin/member/viewer
roles, an audit log, conversation ownership, usage metering from recorded traces, jobs and
scores, a field-level privacy policy at every AI boundary, and data-retention controls.
Not done: Postgres and object storage. The job queue relies on SQLite locking and each account
workspace is its own SQLite file, so a database URL switch would not work without redesigning
those parts.

- **Organisation workspaces with roles.** The Prisma organisation tables already exist; ML data needs to be scoped by organisation.
- **Infrastructure:** an audit log, Postgres for metadata, and object storage for artifacts.
- **Deployment** (needs its own authorization).
- **Billing:** usage metering, reusing the token/cost accounting from M1.
- **PII/DLP:** add a field-level policy in place of the regex blocklist.
- **Security review** and data-retention controls.

## Commercial track (alongside the build, not code)

Interview 5–10 customer-success or revenue-operations leaders at SaaS companies before M3 to confirm which connector comes first and what they would pay. Position the product as an AI retention analyst with measurable lift, against health-score tools (Gainsight, ChurnZero, Vitally). Don't claim uniqueness without evidence.
