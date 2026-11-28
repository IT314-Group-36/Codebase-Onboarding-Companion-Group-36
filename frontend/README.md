# Codebase Onboarding Companion: frontend

React single-page app ("Codeverse") for the Codebase Onboarding Companion. It talks to the FastAPI backend
to connect repositories, explore files, view the dependency map, ask questions about the code and run impact analysis.

## Tech stack

- React 19, Vite, JavaScript (JSX)
- React Router for pages
- React Flow (`@xyflow/react`) and dagre for the dependency graph
- lucide-react icons, plain CSS (design tokens in `src/styles/variables.css`)
- ESLint

## Pages

| Route | Page | Data source |
|---|---|---|
| `/` , `/auth/callback` | Sign in with GitHub | `GET /auth/config`, `/auth/github/login` (redirect), `GET /auth/me` |
| `/dashboard` | Dashboard | `GET /repos` |
| `/connect` | Connect repository (progress polling) | `POST /repos`, `GET /repos/{id}`, `POST /repos/{id}/reindex` |
| `/repository/:repoId` | Repository overview | `GET /repos/{id}` |
| `/explorer/:repoId` | File explorer (symbols, imports) | `GET /repos/{id}/files`, `/files/{path}`, `/symbols` |
| `/dependencies/:repoId` | Dependency map | `GET /repos/{id}/map`, `/impact` |
| `/qa/:repoId` | Ask questions | `/ask/stream`, `/search`, conversation list/create/messages/delete |
| `/onboarding/:repoId` | First-week tasks | `GET /repos/{id}/onboarding-tasks`, `PUT /repos/{id}/onboarding-tasks/{key}/progress`, `POST`/`GET /repos/{id}/issues/sync` |
| `/settings` | Settings | `GET /auth/me`, `POST /auth/logout`; hidden repos stored in localStorage |

## Project structure

```text
frontend/
├── src/
│   ├── components/   reusable UI (graph/, 3d/, buttons, cards, modals)
│   ├── context/      auth context
│   ├── layouts/      app shell (sidebar + topbar)
│   ├── pages/        one file per route
│   ├── services/     api.js (HTTP client), adapters.js (backend -> UI shape), per-feature wrappers
│   ├── styles/       global CSS and design tokens
│   └── utils/        helpers (toasts, GitHub URL and branch rules shared with the backend)
├── public/
├── tests/            white-box unit tests: services/, utils/, graph/, setup.js
├── docs/testing/     guidance for testing categories owned by other team members
├── Dockerfile        dev stage (Vite) and prod stage (nginx)
├── nginx.conf        serves the build and proxies /api to the api container
├── vite.config.js
└── .env.example
```

## Prerequisites

- Node.js 22 (or 20.19+) and npm
- A running backend with GitHub sign-in configured (see the root README); the UI needs it for everything, including login

## Run locally

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. No `.env` file is needed: `VITE_API_BASE_URL` defaults to `/api`, and Vite proxies
`/api/*` to `http://localhost:8000` (the `/api` prefix is removed). Copy `.env.example` to `.env.local` only if you
want to change the API base URL.

Start the backend first, for example from the repository root: `docker compose up db redis api worker`.

## Run with Docker

From the repository root:

```bash
docker compose up --build                                                  # production build served by nginx
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build  # hot reload (Vite in a container)
```

Both serve the app on http://localhost:5173 (change with `WEB_PORT`). In the container, nginx (or the Vite proxy in dev)
forwards `/api` to the `api` service, so the browser only ever talks to one origin.

## Scripts

Run from `frontend/`.

| Command | Description |
|---|---|
| `npm install` | Install dependencies |
| `npm run dev` | Start the Vite dev server |
| `npm run lint` | Run ESLint |
| `npm run build` | Production build into `dist/` |
| `npm run preview` | Preview the production build |

### White-box tests

Install the locked development dependencies with `npm ci` (Node 22).

| Command | Description |
|---|---|
| `npm test` | Run source-derived white-box unit tests once |
| `npm run test:watch` | Rerun tests while editing |
| `npm run test:coverage` | Generate terminal and HTML coverage reports in `coverage/` |

Vitest runs in Node, without rendering React or launching a browser. The suite inspects branches,
conditions, loops, transformations, and error handling in the API client, adapters, GitHub validation,
and dependency-graph algorithms. Network and browser-event dependencies are function stubs.
No backend, database, credentials, DOM environment, or UI testing packages are required.

Coverage is explicitly scoped to five JavaScript modules listed in `vitest.config.js`; it is not
whole-frontend coverage. Minimums: 95% statements/lines/functions and 85% branches.
See [tests/README.md](tests/README.md) for the white-box coverage matrix and commands.

GUI, non-functional, mutation, system/black-box, and acceptance testing are separate assignments.
Their **guidance only** is in [docs/testing/README.md](docs/testing/README.md); no runners, scripts,
test implementations, or CI jobs for those categories are included here. PDF reports are unchanged.

### Chat storage controls

**New chat** starts/reuses an empty conversation without deleting earlier history.
**Delete chat** asks for confirmation, then permanently deletes the current conversation and its
messages on the server. Quota errors are displayed as notifications; deletion is not reported as
failed merely because the server cannot allocate a replacement chat. Older oversized saved messages
are shown as marked bounded excerpts. The browser sends only the new question, conversation ID and
supported target hints; it does not construct or send earlier turns. The backend loads its own bounded
saved context. See `backend/README.md` for chat/progress caps and pagination.

## Backend connection

All requests go through `src/services/api.js`, which prepends `VITE_API_BASE_URL` and turns FastAPI errors into
readable messages (409 not ready, 422 invalid input, 502/503 LLM problems). `adapters.js` converts backend objects
into the shapes the pages expect (for example repo status `queued/indexing/ready/failed` becomes
`pending/analyzing/analyzed/error`).

Authentication: the browser is sent to `/api/auth/github/login`; the backend signs the user in with GitHub and keeps the
session in an HttpOnly cookie, so the frontend never sees a token. `AuthProvider` asks `GET /auth/me` who is signed in,
`RequireAuth` redirects to `/` when nobody is, and any API call that returns 401 signs the user out of the UI.
Always call the API through `/api` (same origin) so the cookie is sent.

Private repositories your GitHub account can access are cloned automatically; the token field on the connect page is
only for using different credentials.

Known gaps between the UI and the API:

- "Remove repository" asks for confirmation, then permanently deletes this user's indexed repository through the API.
- Onboarding progress is saved on the server per user (`task_progress`). Custom tasks added by hand are not supported; the plan always comes from the repository's issues and analysis.
- The repo picker lists the first pages GitHub returns (30 per page, "Load more" fetches the next) and filters them in the browser; a repo further down can be added with "Paste a URL".
- Branches are listed from GitHub (first 100). Names the backend would reject (for example containing spaces) are left out of the dropdown.

## Before you submit changes

```bash
npm run lint
npm test
npm run build
```

All must pass.

---

**IT314 – Group 36** · Codebase Onboarding Companion
