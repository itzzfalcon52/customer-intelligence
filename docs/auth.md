# Email/password accounts

`apps/backend` is the Node/TypeScript account backend. Better Auth handles signup,
login, password hashing, session cookies and logout. Prisma connects it to PostgreSQL
on Neon. Signup signs in immediately. There is no email verification, email delivery,
password recovery or Google provider in this milestone.

## One-time setup

1. Create a dedicated database or development branch in your Neon project.
2. Open **apps/backend/.env**. The file is ignored by Git and already contains a generated
   private `BETTER_AUTH_SECRET`. Keep this secret stable and never paste it into chat.
3. Copy Neon’s pooled connection string into `DATABASE_URL`. Keep `sslmode=require`.
   Optionally put the direct connection string in `DIRECT_DATABASE_URL` for migrations.
4. Run from the project root:

```sh
export PATH="/opt/homebrew/opt/node@22/bin:$PATH"
pnpm setup:backend
pnpm dev
```

`setup:backend` generates Prisma Client and applies the committed migration. It does
not create a local database, replace your existing environment file, or reset tables.
Use a dedicated database so the new tables do not conflict with another application's
User/Session tables. Better Auth does not require its own account or API key.

Open **http://127.0.0.1:5173/signup**. Enter your name, email and a password of at least
12 characters. A successful signup immediately opens `/app`. Logout there, then sign
in at `/login` to check the full flow. No verification link or email provider is needed.
Keep the hostname consistent: `localhost` and `127.0.0.1` have different cookie jars.

## Starting the services

`pnpm dev` starts all three apps. If the frontend is already running in its own terminal,
start only `pnpm dev:backend` in a second terminal. Keep the backend terminal running.

| Service             | Port | Responsibility                                         |
| ------------------- | ---- | ------------------------------------------------------ |
| React/Vite          | 5173 | Marketing and account screens                          |
| New account backend | 3001 | Better Auth, Prisma, Neon and protected account routes |
| Existing FastAPI    | 8000 | Private local ML workflow                              |

Vite forwards `/api/auth/*` and `/api/backend/*` to port 3001, and `/api/v1/*` to Python.
`ECONNREFUSED 127.0.0.1:3001` means the account backend is stopped. If it exits at startup,
read its configuration error, check the Neon connection and run `pnpm setup:backend`.
The backend refuses to announce readiness if the user table is unavailable.

Check the database-backed backend health:

```sh
curl --fail http://127.0.0.1:3001/health
```

## Code map

| File                                 | Purpose                                                                           |
| ------------------------------------ | --------------------------------------------------------------------------------- |
| `src/config.ts`                      | Loads and validates server-only configuration                                     |
| `src/lib/prisma.ts`                  | One Prisma client with the PostgreSQL driver adapter                              |
| `src/lib/auth.ts`                    | Better Auth configuration and organisation plugin                                 |
| `src/middleware/session.ts`          | Rejects missing or expired database sessions                                      |
| `src/app.ts`                         | Auth handler, protected account routes and error handling                         |
| `src/server.ts`                      | Startup, database readiness and shutdown                                          |
| `prisma/schema.prisma`               | User, Session, Account, Verification, Organization, Member, Invitation, RateLimit |
| `prisma/migrations/`                 | Versioned database migration                                                      |
| `apps/web/src/lib/auth.ts`           | Official Better Auth React client                                                 |
| `apps/web/src/pages/AuthPage.tsx`    | Signup/login validation and submission                                            |
| `apps/web/src/pages/AccountPage.tsx` | Session guard, account details and logout                                         |

The `Verification` table belongs to Better Auth's schema; its presence does not enable
email verification. Organisation tables match the framework plugin. The plugin supports
organisation creation and roles; `/api/backend/organizations` returns only the signed-in
user’s memberships. Organisation UI and invitations are not implemented; invitation
and verification/recovery routes are disabled. Do not build duplicate identity tables.

## Session and ownership boundaries

The browser uses a HttpOnly, SameSite=Lax cookie. Passwords are hashed by Better Auth;
they are never stored in plaintext or logged. The frontend does not write credentials or
session tokens to localStorage. The new protected routes read the server-side session;
they never accept a caller-supplied user ID as ownership proof. Logout removes that session.
Production requires an HTTPS `APP_ORIGIN` and Secure cookies. Local services bind to loopback.
Rate limits use the database and ignore forwarded IP headers supplied by callers.

`/api/backend/me` returns only the signed-in user's public account fields.
The core workspace now connects FastAPI through server-validated sessions and isolates
personal account data. Existing legacy customer datasets remain separate. See
[workspace guide](workspace.md).

**Team workspaces (M6, October 30).** `/internal/identity` also returns `organization_id` (the
session's active organisation, only while the user is still a member) and `role`.

- **Isolation:** FastAPI stores an organisation's data in a workspace keyed by
  `sha256("org:" + id)`. Personal workspaces keep their original key, so nothing moves.
- **Creating and switching:** users create a team and switch with Better Auth's organisation
  client (`organization.create` and `setActive`).
- **Members:** `GET/POST/DELETE /api/backend/organizations/:id/members`, `PATCH .../members/:memberId {role}` (owners and admins; the owner's role is fixed) and `DELETE .../members/me` (leave; not for the owner) lists members, and lets
  owners and admins add an existing account by email with the role `admin`, `member` or
  `viewer`, or remove a member. Invitation emails stay disabled.
- **Roles:** `core/permissions.py` enforces them on every request.
  - Members can't change guardrails, connectors, the active model, privacy or retention, and
    can't approve, delete or read the audit log.
  - Viewers are read-only, apart from asking the assistant.
- **Conversations** record their owner, and other members can't list or read them.
- **Not tested here:** the member endpoints have no backend test, because backend database tests
  need `AUTH_TEST_DATABASE_URL`, which isn't set up locally. API-side scoping and roles are
  covered by `apps/api/tests/test_governance.py`.

## Checks

```sh
pnpm --filter @ci/backend check-types
pnpm --filter @ci/backend build
pnpm --filter @ci/web lint
pnpm --filter @ci/web build
pnpm test:backend
```

The backend suite runs configuration checks by default. Real PostgreSQL integration
checks run only with `AUTH_TEST_DATABASE_URL` pointing to a separate **local** database
whose name ends in `_test`; they reject Neon and nonlocal hosts. Apply the migration to
that disposable test database before running. Tests exercise immediate signup, password
hash storage, invalid login, HttpOnly cookies, protected routes, origin rejection,
organisation ownership, logout and login. They clean up only their own generated fixtures.

References: [Better Auth Prisma adapter](https://better-auth.com/docs/adapters/prisma),
[Express integration](https://better-auth.com/docs/integrations/express),
[organisation plugin](https://better-auth.com/docs/plugins/organization).

The account-to-ML bridge uses the generated server-only INTERNAL_API_SECRET. The setup
helper adds it when absent and preserves an existing value. Never put it into a Vite variable.
