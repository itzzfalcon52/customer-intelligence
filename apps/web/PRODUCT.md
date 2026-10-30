# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The site serves two audiences at once: customer-success and RevOps leads at B2B SaaS companies
deciding whether to try it, and hackathon judges who need to see clearly how Nemotron is used.

The primary user is a customer success or revenue operations lead at a B2B SaaS company. They are
not an ML specialist. They come to the product to answer three questions: which accounts are at
risk, why those accounts, and what to do about them within a fixed budget. A data or RevOps
analyst is a secondary user who connects data and sets up the churn model once. Nobody else needs
to see model internals.

## Product Purpose

An AI retention analyst for subscription businesses. It turns historical account data into a
confirmed churn definition and a fairly compared model. It then ranks current accounts by risk,
explains what is associated with that risk, and plans evidence-backed contact decisions:
detect → explain → act → measure. Success means fewer surprise churns and contact lists the team
can defend with numbers.

## Positioning

Every number shown to the user comes from deterministic computation, not from the language model.
Investigations plan hypotheses, run real analyses, and pass a code-based verifier that withholds
any statement the evidence does not support. Chat answers are checked the same way. Nothing is
sent to a customer, and no financial or causal claim is made, without evidence or explicit
approval.

## Operating Context

- **Daily:** a ranked account list and a weekly look at what changed in risk.
- **Weekly or campaign-based:** budget planning for retention plays and reviewing outreach drafts.
- **Occasionally:** an analyst uploads history (CSV/Excel today), confirms the churn label and
  pre-outcome inputs, trains, and scores a current customer sheet.
- **AI provider:** NVIDIA Nemotron via Nebius. Only aggregates, computed drivers and
  pseudonymous account labels (A1, A2…) are sent, never raw customer rows or real account IDs.
- **Daily loop:** a scheduled check re-scores the latest data with the active model, checks
  whether customers changed, measures outcomes once known, and (with workspace consent) has
  Nemotron write a verified brief: what changed, accounts to call first and why, and a recommended
  play cited from the team's own playbooks.
- **Accounts:** personal workspaces plus team workspaces with owner, admin, member and viewer
  roles enforced by the server.

## Capabilities and Constraints

- **Implemented:**
  - upload and profiling;
  - churn task confirmation, with leakage checks;
  - bounded model comparison (baseline, logistic regression, random forest, XGBoost);
  - calibration;
  - a reserved final test;
  - batch scoring with ranked export;
  - analyses (importance, segments, contact curves);
  - retention studio (ROI scenario, draft-only outreach, rule challenger);
  - a streaming Copilot with traces;
  - verified investigations;
  - multi-table account sources (synthetic SaaS demo or CSV bundle) with point-in-time snapshots
    and time-ordered evaluation;
  - an active-model registry, scheduled checks, drift and measured performance;
  - holdout groups and measured outreach lift with 95% intervals;
  - Nemotron daily briefs and per-account reasons, each sentence verified in code;
  - playbook search with citations;
  - an approvals Inbox, autonomy levels, a kill switch and AI token budgets;
  - team workspaces, an audit log, usage, a privacy policy and data retention;
  - uploads up to 200 MB / 1 million rows (configurable).
- **Honesty rules that UI copy must respect:**
  - features are associations, not causes;
  - ROI and budget outputs are assumption-based scenarios, not measured savings;
  - outreach is draft-only;
  - uncalibrated outputs are risk scores, not probabilities;
  - synthetic or demo data is labelled as such.
- **Available:** read-only Stripe and HubSpot connectors feeding the daily check, matched by
  domain, approved plays as HubSpot tasks, and per-person email digests after each check.
- **Coming soon** (never present as available): live connectors (Salesforce, Intercom,
  Zendesk), Slack digests, and public hosting. Nemotron
  reading raw support-ticket text is not built.
- **Terminology for the primary user:** "risk score", "accounts to contact", "why this account",
  "plays". ML terms (experiment, run, calibration, average precision) belong in model details.

## Brand Commitments

- **Name: Holdfast** (October 30, 2026, chosen by the user's delegation, may still change). A
  holdfast is the root-like anchor that keeps kelp attached to rock through tides; the product
  keeps hold of customers who would otherwise drift. The earlier working name was "Customer
  Intelligence".
- **AI:** NVIDIA Nemotron on Nebius is a named, visible ingredient ("Powered by NVIDIA Nemotron on
  Nebius"). No partner logos or endorsement claims.

## Evidence on Hand

- A seeded synthetic SaaS account dataset (`apps/api/evals/dataset.py`), labelled synthetic.
- Recorded agent eval results (`docs/backend.md`).
- The live product itself.

Absent, and must not be fabricated: customer logos, testimonials, case studies, benchmark claims,
pricing commitments and uptime or security certifications.

## Product Principles

1. **Evidence over eloquence.** Show the number, its interval and where it came from before any
   narrative.
2. **The task before the pipeline.** Lead with accounts and actions; model mechanics stay
   available but out of the way.
3. **Dense but calm.** High information density for a daily tool, with restraint in colour and
   motion.
4. **Honest defaults.** Sensible defaults for non-specialists, with limitations stated where
   decisions are made.

## Accessibility & Inclusion

Target WCAG 2.2 AA: contrast, keyboard access to every action (including the Ask panel), visible
focus, reduced-motion support, and status not conveyed by colour alone (risk levels carry text
labels).
