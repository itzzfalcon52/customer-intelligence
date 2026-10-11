# Customer Intelligence

Turborepo skeleton with a React/Vite/TypeScript frontend and Python FastAPI backend.

## Structure

- `apps/web`: frontend; empty `components`, `pages`, `hooks`, and `lib` folders.
- `apps/api`: backend; empty API, schemas, models, services, ML, and agent packages.
- `packages`: reserved for shared packages.
- `scripts`: connects the Python environment to Turborepo.

## Setup

Use Node.js 22.12+ (Node 22 recommended), pnpm 11, and Python 3.13.

```sh
pnpm install
pnpm setup:python
pnpm dev
```

Dependencies are already installed locally. Frontend: http://127.0.0.1:5173.
Backend API docs: http://127.0.0.1:8000/docs.

```sh
pnpm build
pnpm lint
pnpm check-types
```

Python dependencies are declared in `apps/api/pyproject.toml`, locked in
`apps/api/uv.lock`, and exported in `requirements.txt` and `requirements-dev.txt`.
The local Python environment is `apps/api/.venv`.

Installed backend libraries include FastAPI, Pydantic, pandas, NumPy,
scikit-learn, XGBoost, SQLModel, LangChain, LangGraph, and the OpenAI SDK.
Frontend libraries include React Query, React Router, Recharts, Lucide, and Zod.
These libraries are installed for future development; no product features are implemented.

Copy `.env.example` when setting up another machine. Keep credentials in the backend environment.
On macOS, XGBoost requires OpenMP (`brew install libomp`); it is already installed here.
