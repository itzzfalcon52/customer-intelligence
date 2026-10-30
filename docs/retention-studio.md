# Retention Studio: implementation and walkthrough

This milestone moves Nemotron into bounded, reviewable actions. It does not send customer messages,
connect to a live CRM, or claim that an intervention has been proven to work.

## Try it

1. Start `pnpm dev` and `pnpm worker:api` from the project root. Restart an already running worker
   after updating its code. Sign in normally; account validation and workspace isolation still apply.
2. Upload customer history in **Customer data**. For a quick demonstration, **Connections → Load
   synthetic demo** imports 600 clearly labelled generated records. HubSpot/Stripe are labelled
   planned; there is no fake connected-account badge or live synchronization.
3. Review the suggested outcome, ID and inputs. Confirm the exact positive label and pre-outcome
   feature availability. Suggestions are starting points, not verified business facts.
4. In **Review and train**, allow provider processing and choose **Review with Nemotron**. It reviews
   column names, types, missingness and aggregates; no raw five-row sample is sent. Findings cover
   every selected input. Obvious outcome-date/reason fields are excluded from its proposed feature
   list even if the model misses them. Ambiguous fields require review.
5. **Use reviewed inputs** creates a new confirmed task. Original tasks/runs remain immutable.
   Training also rejects the small conservative list of obvious post-outcome field names.
6. Recommended UI defaults: four additional search variants, three training CV folds and a cutoff
   that balances F1. Select **precision with a recall floor** when false alerts matter more. Enable
   the optional automatic executive briefing if you want a provider-written summary after training.
7. Review validation results and the precision/recall curve. **Ask AI about this result** attaches
   dataset, task and experiment context automatically. More context is tucked into an optional panel.
8. Score a separate current-customer sheet. Optionally request five general outreach drafts after
   scoring. This automatic option shares no customer feature values. Its failure does not discard
   successfully computed scores.
9. Open **Retention studio**. Choose a budget, contact cost, offer cost, retained value and assumed
   save rate for the same retention period. A scoring batch can supply the actual population and a
   risk-ranked shortlist. Zero contacts is a valid scenario outcome.
10. In **Prepare outreach**, supply a product, approved next step/offer, and optionally select account
    facts for personalization. Up to five highest-risk customers are considered, independently of
    value ranking. IDs stay local. The UI shows draft text, evidence fields and copy controls.
11. **Review the evidence** generates a three-paragraph briefing or challenges the model with a
    simple rule. Saved drafts, briefings and rules can be reopened inside the studio.
12. Use **Settings → Check AI connection** for a small live provider check without customer data.

## What is computed, and what is generated

| Action             | Nemotron's role                                                                | Backend's role                                                                                                                              |
| ------------------ | ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Schema review      | Suggest keep/exclude/review, reasons and questions                             | Validate column scope; enforce known exclusions; save proposal; require confirmation before creating a revised task                         |
| Training           | Explain the recorded comparison/plan                                           | Train real pipelines, compare validation results, calculate training CV and cutoff policy                                                   |
| Outreach           | Write email/SMS drafts from permitted account facts and model sensitivity      | Pick highest-risk rows, calculate reference perturbations, omit IDs/sensitive fields, validate row/evidence scope, save drafts              |
| Rule challenger    | Propose at most three AND conditions from training summaries                   | Interpret a restricted comparison DSL and calculate actual validation metrics; no generated Python execution                                |
| ROI scenario       | Request calculations through a typed tool after asking for missing assumptions | Evaluate affordable contact counts, reserve costs, estimate scenarios from validation contact precision, return shortlist and evidence size |
| Executive briefing | Explain recorded metrics in three paragraphs                                   | Save evidence and generated narrative separately; preserve a computed summary when the provider is unavailable                              |

## Training changes and limits

Extra trials are now interleaved across model families. The first additional trial explores a
regularized shallow XGBoost variant, rather than spending the first two trials only on Logistic
Regression. Search remains a bounded maximum of eight additional candidates. No added dependency
or GPU is needed.

`TrainRequest` adds `cv_folds` (0, 3, 5), `threshold_policy` (`fixed`, `f1`,
`precision_at_recall`), `minimum_recall`, and `generate_briefing`. Existing clients retain fixed-cutoff,
no-CV behavior. UI defaults opt into the stronger comparison. Each CV fold fits its own preprocessing
pipeline on training-fold rows. Candidate training-CV AP mean/std are reported as stability checks.
The winner is still chosen by validation AP; CV does not replace that legacy selection rule.

Automatic cutoff policies use three-fold out-of-fold predictions from training rows of the selected
model. The recall floor applies to those development predictions; it is not a guarantee for new
customers. All candidates' confusion counts are recalculated at the resulting common cutoff.
Changing the cutoff does not improve the underlying AP or ROC-AUC. A validation curve shows that
tradeoff. Candidate search and policy choices still create development optimism; final test results
must be revealed only after choices are frozen. There is no automatic test-set tuning, target
leakage, seed shopping, oversampling of validation/test rows, or fabricated performance target.

The preprocessing source file is unchanged so existing fitted pipelines remain loadable. Old runs
retain their original inputs, settings and metrics. New defaults do not silently rewrite saved runs.

## API surface

All routes are under `/api/v1`, use the existing account boundary, and use scoped workspace settings.

| Method and path                   | Purpose                                                                                                                      |
| --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `POST /retention/schema-review`   | `task_id`, `provider_consent:true`, UUID `idempotency_key`                                                                   |
| `POST /retention/apply-schema`    | `review_id`, `features_available_at_prediction:true`                                                                         |
| `POST /retention/campaign`        | `score_id`, product, approved offer, channel, permitted features, consent/key                                                |
| `POST /retention/roi`             | `run_id`, budget, contact/offer costs, assumed save rate, retained value, currency, population; optional matching `score_id` |
| `POST /retention/rule-challenger` | `run_id`, consent/key                                                                                                        |
| `POST /retention/briefing`        | `run_id`, consent/key                                                                                                        |
| `POST /retention/provider-check`  | Small connectivity request, no customer data                                                                                 |
| `GET /runs/{id}/briefing`         | Automatic briefing status or computed fallback                                                                               |
| `GET /scores/{id}/campaign`       | Automatic draft-generation status                                                                                            |

AI action artifacts share the existing `analyses` storage, deletion cascade and account isolation.
An idempotency key replays the same completed action; changed input under the same key returns 409.
A short SQLite lease prevents simultaneous duplicate execution. Provider failure releases the lease
and allows retry. No SQLite write transaction stays open during inference. A failed request can still
incur provider usage; persisted idempotency is not a provider billing guarantee.

`AssistantRequest.allow_actions:true` exposes scoped `analyze_schema_semantics`,
`generate_retention_campaign`, `calculate_intervention_roi`, `challenge_business_rule` and
`generate_executive_briefing` tools. Scope and typed arguments are checked for the whole batch before
execution. The model cannot enlarge its permitted feature list, supply its own consent/key, choose
another account's resource, execute Python, send messages or mutate an existing task. Chat-generated
outreach uses only the caller's `campaign_features` and `approved_offer`; default features are empty.

## Provider reliability

The shared adapter classifies configuration, connection, timeout, credential, rate-limit and invalid
structured-response failures. Defaults are a 60-second provider call with a 20-second connect timeout,
a bounded transport retry for connection establishment only, no SDK inference retries, and a
180-second conversation loop budget. An in-progress provider call or nested action can finish after
that loop deadline, but a subsequent loop call is refused. At most eight total model calls (including nested AI actions), six outer loop calls, and eight tool calls are permitted.

`CI_NEBIUS_TRUST_ENV=false` avoids accidentally inheriting proxy settings. Set it intentionally if
your network requires an environment proxy. TLS verification stays enabled. For the exact configured
Lightning model, `CI_NEBIUS_ENABLE_THINKING=false` uses the documented chat-template control to leave
more output budget for tool results. Unknown replacement models do not receive that model-specific
option. Structured responses are Pydantic-validated whether delivered as the forced function or a
JSON message; arbitrary prose is rejected.

Provider documentation: [Nebius function calling](https://docs.tokenfactory.nebius.com/ai-models-inference/function-calling),
[NVIDIA Lightning controls](https://docs.nvidia.com/nim/large-language-models/2.0.10/get-started/advanced/get-started-nemotron-3.5-lightning.html).
Network availability, provider capacity and model output quality can still fail. Do not present a
connectivity probe or mocked test as proof every future request will work.

## Honest financial and outreach interpretation

Budget calculations use validation precision at a comparable contact fraction rather than treating
uncalibrated current risk scores as true churn probabilities. They assume this ranking transfers to
the current population. Cost reserves `contact_cost + offer_cost` for every contacted customer, even
if not everyone would redeem the offer. Benefit assumes a user-supplied constant fraction of actual
churners is saved and a specified retained value. No causal effect or measured savings is established.
The selected validation sample size and a Wilson precision interval are returned; the interval does
not account for repeated model/policy selection or deployment shift. Small samples are flagged.

Personalization is opt-in per request and feature list. Names, IDs, sensitive/demographic field names,
free text and high-cardinality categories are blocked. The allowlist is still not a full DLP system:
users must choose appropriate account fields and review drafts. Local model sensitivity is a reference
perturbation, not SHAP or evidence a feature caused churn. Nothing is sent to customers.

A successful model/scoring job with an AI follow-up failure remains successful with a separate
failure status. Automatic follow-ups can be interrupted when the worker is stopped; they are bounded
optional work, not an external delivery service or a resumable distributed workflow.
