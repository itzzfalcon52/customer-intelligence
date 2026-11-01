> October 15 update: see [Retention Studio](retention-studio.md) for the active AI actions,
> automatic briefings/drafts, training CV and decision policies. This supersedes older limitations below.

# Customer Intelligence workspace

The signed-in application lives at **http://127.0.0.1:5173/app**. Neon connectivity,
account migrations and a synthetic end-to-end ML workflow were verified on October 13.
Email/password signup signs in immediately; no email verification or Google flow is enabled.

## Start and try it

From the project root, with Node 22 selected:

```sh
export PATH="/opt/homebrew/opt/node@22/bin:$PATH"
pnpm dev
```

In a separate terminal:

```sh
pnpm worker:api
```

Keep both terminals running. `pnpm dev:web` alone starts only Vite. The app uses port
5173, the account backend 3001, and FastAPI 8000. The workspace displays whether the
worker is running. If services are already running, do not start duplicates on those ports.

1. Sign in and open Customer data. Upload labeled customer history as CSV or Excel.
2. Open its profile to inspect columns, missing values, numeric summaries and preview rows.
3. Set up a prediction: target, positive class, ID and pre-outcome features. Validate the
   target and explicitly confirm feature availability.
4. Review the saved task and comparison plan. Optionally inspect the split and request
   up to eight extra search trials. Choose the threshold, then start the experiment.
5. Follow Activity; jobs run independently of the page. Cancel queued/running work there.
6. Open the results. Review validation metrics, comparison chart, failed candidates,
   warnings, confusion counts and parameters. Create diagnostics or calibrate before the final test.
7. Explicitly confirm final evaluation. Its cached test results freeze that task; do not use
   them to retune or select another run on the same test customers.
8. Upload a separate current-customer sheet. Score it with a saved run and a contact budget.
   Optionally choose risk × customer value. Review customers and export a ranked CSV.
9. Queue a customer explanation from the shortlist and open its result in Insights.
10. Open Copilot, select the relevant context and read the provider notice. Grant consent
    before sending a question. Expand tool events to inspect the evidence reference.

## Implemented features and routes

| Feature                                                                                                        | Screen                      |
| -------------------------------------------------------------------------------------------------------------- | --------------------------- |
| Overview, real recent data/activity, service status                                                            | `/app`                      |
| CSV/Excel, sheet selection, file validation, dataset catalog                                                   | `/app/datasets`             |
| Types, completeness, duplicates, distinct values, numeric summaries, row preview                               | `/app/datasets/:id`         |
| Target validation, class counts, IDs, features, recorded business assertion                                    | `/app/datasets/:id/setup`   |
| Saved task selection, four model families, plan, split, bounded search, threshold                              | `/app/experiments/new`      |
| Run history, selection of 2–5 runs, provenance-aware comparison                                                | `/app/experiments`          |
| Validation metrics/chart, final test, confusion counts, calibration, diagnostics, leakage demo, report         | `/app/experiments/:id`      |
| Polling, heartbeat/stage, cancellation, failure message, result navigation                                     | `/app/jobs`                 |
| Current-sheet scoring, contact budget, risk/value ranking                                                      | `/app/customers/new`        |
| Scoring history, paginated customer priorities, CSV export, explanation jobs                                   | `/app/customers` and `/:id` |
| Importance, contact curve, score reliability, segments, rule benchmark, reference sensitivity, leakage results | `/app/analyses` and `/:id`  |
| Context-scoped questions, evidence events, conversation recovery, explicit training permission                 | `/app/copilot`              |
| Account, worker/API status, provider notice, limits, storage explanation                                       | `/app/settings`             |
| Dataset deletion with explicit permanent-delete/cascade confirmation                                           | Dataset profile             |

The data/history catalogs are paginated. Task and context selectors load the latest 100
records; the conversation selector loads the latest 100 conversations for the dataset.
They are bounded selectors, not an unlimited archive search. Technical disclosures retain
all backend metrics/provenance so the simplified visuals do not hide supporting evidence.

## Code and state

- `src/workspace/pages/`: feature screens, loaded by route.
- `src/workspace/types.ts`: typed backend contracts.
- `src/workspace/api.ts`: restricted same-origin requests, upload checks and authenticated downloads.
- `src/workspace/queries.ts`: TanStack Query hooks, mutation invalidation and bounded job polling.
- `src/workspace/store.ts`: Zustand UI state (menu and provider consent); no persisted customer data.
- `src/workspace/Shell.tsx`: session guard, sidebar, service status, account transitions and logout.
- `src/workspace/ui.tsx`, `format.ts`, `charts.tsx`: shared controls, formatting and charts.
- `src/styles/workspace.css`: workspace theme, layout and responsive behaviour.

TanStack Query owns server records. Query keys include the authenticated user ID; cached
queries are cancelled/cleared at logout or an account change. Zustand owns temporary UI
preferences only. No files, passwords or session tokens are written to localStorage.
Jobs poll while active; regular catalog data is not polled continuously. Worker status polls
once every ten seconds. Charts and page code are lazy-loaded; charts avoid costly entry animations.

## Authentication and storage

FastAPI validates the browser's Better Auth session against a private Node endpoint on
every protected request. A shared server-only `INTERNAL_API_SECRET` protects that endpoint;
Vite never proxies `/internal`. The session must still exist in Neon. Browser-provided user
or workspace IDs do not select storage. Missing/expired sessions return 401; an unavailable
account service returns 503. Account mode is the default; explicit `CI_AUTH_MODE=private`
preserves the direct CLI learning path and its optional static token.

The verified user ID determines a SHA-256-named private workspace under `.data/workspaces/`.
Each account gets its own SQLite metadata, uploads, splits, jobs, pipelines, scores, analyses
and conversations. Existing legacy `.data` records are preserved separately and are not
claimed by a newly created account. The worker discovers initialized account workspaces
and processes their jobs under the existing single-worker lock.

**Neon/PostgreSQL holds identity and organisation records.** It does not currently hold
Python workflow metadata or large uploaded files. **S3 is unnecessary for local use.**
Local workspace storage must remain on a durable disk. A cloud deployment needs durable
shared artifact storage (S3 or equivalent), worker access, backups and a metadata deployment
plan; merely adding an S3 bucket does not convert this into a scalable deployment.

Organisation records exist in Better Auth, but ML collaboration/membership roles are not
yet connected: this release explicitly presents personal account workspaces. Google,
CRM/billing/support connectors, outreach, time/group splits, regression and other P2 work
remain outside this implementation. No cloud deployment or external outreach was performed.

## Verification

The backend suite includes account isolation and failure-closed session tests. The live
HTTP smoke pass used two disposable Neon-backed QA accounts and 480 synthetic rows:
seven compute jobs completed, reports/CSV exported, and cross-account data access was rejected.
A live Nemotron inspection and a saved-run request retrieved the required tools before answering.
Provider calls can still fail under the enforced time/tool budgets; these failures remain visible.

Desktop and phone visuals were checked on a separate synthetic-only preview harness;
production session guarding remains enabled. This visual preview does not authenticate
into or expose the user's personal account. QA records and temporary test services are
cleaned up after verification. No real customer sheet or API credential was used in the preview.

References: [TanStack Query polling](https://tanstack.com/query/latest/docs/framework/react/guides/polling),
[Zustand store API](https://zustand.docs.pmnd.rs/reference/apis/create),
[Amazon S3 storage](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html).

## Investigate (M2)

`/app/investigate` asks a churn question of a trained experiment. While it runs, you see the
hypotheses, analyses and verifier steps live. The result is a verified report: findings link to
their evidence tables, and withheld statements are listed with the verifier's reasons. Copilot
answers show whether their numbers were checked against tool outputs. A per-turn trace panel
shows model and tool calls, latency and tokens. Investigations are saved as Insights.

## Navigation (simplified October 30, 2026)

The sidebar leads with the everyday path for a customer-success team. Expert tools sit under a
collapsible **Advanced** group, which remembers whether it was open.

- **Get set up:** a four-step checklist (data → churn definition → model → scores). It and the
  per-page stepper disappear once the first batch is scored.

| Sidebar          | Path                                                                                                                             | Contents                                                                          |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Home             | `/app`                                                                                                                           | Onboarding and one-click demo until the first scoring, then the risk dashboard    |
| At-risk accounts | `/app/scores`, `/app/scores/new`, `/app/scores/:id`                                                                              | Scoring batches (optional 20% holdout), ranked accounts, export, Explain          |
| Retention plays  | `/app/plays`                                                                                                                     | Assign a play (to the Inbox), budget plan, outreach drafts, briefing, rule check  |
| Results          | `/app/monitoring`, `/app/monitoring/:id`                                                                                         | Did outreach work (holdout lift), automatic check, change and outcome reports     |
| Ask AI, Inbox    | `/app/ask`, `/app/inbox`                                                                                                         | Assistant; approvals (training, retraining, plays) and the digest                 |
| Data             | `/app/data`, `/app/data/:id`                                                                                                     | Uploads and quality profile; links to connectors and sources                      |
| Advanced         | `/app/churn`, `/app/models`, `/app/investigate`, `/app/analyses`, `/app/playbooks`, `/app/sources`, `/app/jobs`, `/app/settings` | Definitions, models, investigations, analyses, playbooks, sources, jobs, settings |

The plain-language copy is deliberate:

- quality reads "N× better than random";
- monitoring reads "Did customers change?", "How did predictions hold up?" and
  "Did outreach work?";
- autonomy levels are "Just report", "Suggest" and "Ask me before acting".
  Technical values (AP, PSI) remain on the detail pages.

**Home** leads with Nemotron's brief: a headline, what changed, accounts to call first (with
playbook citations) and a recommended play with an "Assign this play" button that pre-fills
Plays. **At-risk accounts** shows a checked Nemotron note, or the computed drivers, under each of
the top 15 accounts.

**Team** (`/app/team`, also reached from the top-bar workspace pill) is where users create a team
workspace, switch workspaces, and see what each role can do (the table comes from the server's
rules).

- Owners and admins add members by email, change roles, remove members and rename the team.
- Members and viewers see the member list and their own access, and can leave.
- Elsewhere in the app, admin-only controls (Approve and Reject, Make active, automation, privacy,
  retention, schedule settings) are hidden or read-only for members and viewers.

**Settings** holds the account, service status, the privacy policy, data retention, usage,
workspace memory and (for owners and admins) the audit log.

**Connectors** (Data sources → Connectors, also linked from the Data page as "Connect billing or
CRM"): grouped as **Billing** (Razorpay, Zoho Billing, Stripe) and **CRM and support** (Zoho CRM,
HubSpot). Each card has a collapsed connect form (one key for Stripe/HubSpot; key ID + secret for
Razorpay; region, client ID, client secret and one-time code for Zoho), then sync status and
counts, Sync now, Train from this data and Disconnect; admins only manage them. CRM cards ask
which date records churn and can allow task creation; billing cards can match with a CRM and
show the match rate and any sync notes. Plays can be delivered as tasks in any CRM that allows
it. Salesforce, Freshdesk/Freshsales, Chargebee, Intercom and Zendesk show as "Coming soon".

**Renewal radar** (`/app/renewals`, main navigation after At-risk accounts): 30/60/90-day tabs,
stats (renewing, value renewing, value on high-risk accounts, set to cancel), and a table with
the triage swatch and rank, renewal date or "overdue", last payment and cycle, risk badge and
score bar, Nemotron's reason line and holdout/set-to-cancel badges. Sort by risk, date or value;
export CSV. Without renewal data it explains how to connect billing. Home shows a one-line
"renewing in 30 days" link when data exists. Currency comes from workspace memory.

**Connector guide** (`/app/guides/connectors`, Advanced → Connector guide, and "Setup guide" /
"Step-by-step guide" links on every connector card): step-by-step instructions per provider
(where to create the key, exact scopes, region, revoking access), matching, daily checks and a
troubleshooting table of Holdfast's real error messages. Anchors: `#razorpay`, `#zoho`,
`#zoho-billing`, `#zoho-crm`, `#stripe`, `#hubspot`. The workspace shell scrolls to `#anchors`
after lazy pages load.

**Email digest:** Settings → Email digest lets each person turn on an email after every
automatic check and send themselves a test. Results links to it. Slack is still "Coming soon".

- **Demo pipeline:** "Run the demo in one click" (Overview, Data sources or the command
  palette). It uploads the labelled synthetic CSV, saves the obvious churn definition
  (`Churn = Yes`) and queues default training through the normal API endpoints. The worker
  must be running.
- **Ask AI:** a slide-over drawer opened with ⌘J or the top-bar button. It uses the model or
  scoring batch in the URL as context. `/app/ask` is the full page.
- **Command palette:** ⌘K.
- **Old paths:** every earlier path (`/app/datasets…`, `/app/experiments…`, `/app/setup…`,
  `/app/accounts…`, `/app/insights…`, `/app/model…`, `/app/customers…`, `/app/retention`,
  `/app/copilot`, `/app/connections`) redirects, keeping its ID and query string.
