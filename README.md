<p align="center">
  <img src="frontend/assets/opai-logo.png" alt="OPAI logo" width="112" />
</p>

<h1 align="center">OPAI — Operating Agent</h1>

<p align="center">
  <strong>A personal AI workspace to plan your day, learn with intent, build projects, and turn context into action.</strong>
</p>

<p align="center">
  <a href="https://opai.live/">Live product</a> ·
  <a href="https://github.com/tiru-venkatesh/opa">Source repository</a> ·
  <a href="#getting-started">Get started</a> ·
  <a href="#api-reference">API reference</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/AI-Groq%20%7C%20Gemini%20%7C%20OpenRouter-5A45FF" alt="Groq, Gemini and OpenRouter" />
  <img src="https://img.shields.io/badge/Frontend-HTML%20%7C%20CSS%20%7C%20JavaScript-E34F26?logo=html5&logoColor=white" alt="HTML CSS JavaScript" />
  <img src="https://img.shields.io/badge/Status-Active%20Development-orange" alt="Active development" />
</p>

---

## What is OPAI?

**OPAI (Operating Agent)** brings personal planning, academics, projects, applications, opportunities, resume work, and AI assistance into one connected workspace.

Most productivity tools store tasks. OPAI is being built to connect the task with the reason behind it: your goals, current commitments, past work, deadlines, and relevant documents. Its AI layer can use that context to help plan, research, draft, prioritize, and prepare actions for review.

The repository contains a multi-page static frontend and a Python/FastAPI backend. The project is actively evolving, and some integrations depend on external provider configuration.

## Product areas

| Area | What it helps with |
|---|---|
| **Today** | Review priorities, due work, reminders, suggested actions, and daily planning. |
| **KARNA / JARVIS** | Chat with the assistant about your workspace and use context-aware AI workflows. `JARVIS` remains in some API names. |
| **Briefs** | Generate focused daily, exam, DSA, project, application, outreach, decision, and recovery briefs. |
| **Opportunities & applications** | Collect opportunities, assess fit, track application stages, identify blockers, and prepare next steps. |
| **Projects** | Keep project details, progress, milestones, and blockers together. |
| **Academics** | Organize courses, syllabus material, exams, study blocks, and study plans. |
| **DSA planner** | Track a roadmap, plan practice sessions, and record progress and streaks. |
| **Resume Lab** | Import resume content, review and compare versions, tailor resumes, improve bullet points, and export documents. |
| **Knowledge & RAG** | Add documents and notes, retrieve relevant passages, and ask questions with source references. |
| **Outreach & faculty discovery** | Organize contacts and follow-ups and prepare context-aware outreach drafts. |
| **Actions & Outbox** | Separate AI-generated recommendations and drafts from consequential actions that need review or approval. |

The availability of an individual workflow depends on its provider keys, account configuration, and deployment setup.

## How the AI layer works

OPAI uses a layered approach so language-model output is not treated as unrestricted authority to change user data.

```text
User request
    │
    ▼
KARNA local intent + privacy + quota routing
    │
    ├── Groq — fast chat, coding, workspace-safe default
    ├── Gemini — complex reasoning and policy-approved study/document/image tasks
    └── OpenRouter — non-private general-chat fallback
    │
    ▼
Backend validation and workflow logic
    │
    ├── Retrieve relevant user context (RAG)
    ├── Read or update application data
    └── Prepare a draft or proposed action
    │
    ▼
Review / approval when required
    │
    ▼
Execute allowed action and record activity
```

### Context-aware retrieval (RAG)

The knowledge pipeline can parse **PDF, DOCX, TXT, Markdown, and CSV** files, split their contents into chunks, create embeddings, and retrieve relevant passages for a question. The default local embedding option is FastEmbed with `BAAI/bge-small-en-v1.5`; a lightweight hashed bag-of-words fallback is available. Changing the embedder may require rebuilding the index.

RAG is retrieval-based context assembly; it does **not** fine-tune a model on uploaded personal documents. Retrieved document text should be treated as data, not as instructions.

## Architecture

```mermaid
flowchart TD
    U[User] --> FE[Static frontend<br/>HTML · CSS · JavaScript]
    FE -->|HTTPS / REST| API[FastAPI backend]
    API --> AG[Agent router and workflow services]
    AG --> MR[KARNA model router]
    MR --> GROQ[Groq API]
    MR --> GEM[Gemini API]
    MR --> OR[OpenRouter]
    AG --> RAG[RAG and retrieval layer]
    API --> DB[SQLAlchemy data layer]
    DB --> SQLITE[(SQLite)]
    DB --> PG[(PostgreSQL optional)]
    RAG --> EMB[FastEmbed or hash fallback]
    AG --> AP[Approval / Outbox / audit flow]
```

**Frontend and backend are separate deployable pieces.** The frontend under `frontend/` is designed for static hosting. The backend under `backend/` is a persistent FastAPI process and also includes a `static/` copy of selected UI files for its own page routes.

## Tech stack

| Layer | Technologies |
|---|---|
| Frontend | HTML, CSS, vanilla JavaScript, browser `localStorage`, web app manifest and service worker |
| API | Python, FastAPI, Uvicorn, Pydantic |
| Persistence | SQLAlchemy, SQLite by default, PostgreSQL supported |
| AI | KARNA routing over Groq, Gemini and OpenRouter; optional legacy providers remain configurable |
| Retrieval | FastEmbed, `BAAI/bge-small-en-v1.5`, Python-side similarity/keyword retrieval |
| Document processing | `pypdf`, `python-docx`, `python-multipart`, ReportLab for PDF export features |
| Hosting pattern | Vercel or another static host for the frontend; Render, Railway, Fly.io, or a VPS for the backend |

## Repository layout

```text
opa-main/
├── frontend/                  # Multi-page static application and landing page
│   ├── landing.html           # Public homepage entry
│   ├── login.html              # Redirects to the workspace while sign-in is paused
│   ├── app.html                # Main application shell
│   ├── today.html              # Daily workspace
│   ├── academics*.html         # Academic workflows
│   ├── opportunities.html      # Opportunity pipeline
│   ├── projects.html           # Project workspace
│   ├── resume-lab.html         # Resume tools
│   ├── super-chat.html         # KARNA/JARVIS chat UI
│   ├── assets/                 # Logo and launch media
│   └── vercel.json             # Static-host routing and headers
├── backend/
│   ├── main.py                 # FastAPI application and core routes
│   ├── database.py             # SQLAlchemy engine and data models
│   ├── agent/                  # Routing, decisions, fallbacks, approvals
│   ├── workflows/              # Daily planning and workflow logic
│   ├── briefs/                 # Brief generation and lifecycle
│   ├── retrieval/              # Retrieval and trust filtering
│   ├── tests/                  # Backend and contract tests
│   ├── static/                 # UI assets/pages served by FastAPI
│   ├── requirements.txt        # Python dependencies
│   └── .env.example            # Environment-variable template
├── ARCHITECTURE.md             # KARNA's current backend architecture
├── CHANGELOG-v*.md             # Development history
└── README.md
```

## Getting started

### 1. Requirements

- Python **3.10 or newer**.
- At least one backend API key: Groq, Gemini, or OpenRouter.
- A modern browser.
- Optional: PostgreSQL for a persistent production database.

### 2. Start the backend

From the repository root:

```bash
cd backend
python -m venv .venv
```

Activate the environment.

**Windows PowerShell**

```powershell
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
```

**macOS / Linux**

```bash
source .venv/bin/activate
cp .env.example .env
```

Install dependencies:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Open `backend/.env` and configure the provider keys you want to enable. Keys stay on the backend:

```dotenv
GROQ_API_KEY=your_groq_api_key
GEMINI_API_KEY=
OPENROUTER_API_KEY=
KARNA_DEFAULT_MODE=auto
KARNA_ENABLE_FALLBACK=true
KARNA_ENABLE_PAID_MODELS=false
KARNA_GEMINI_WORKSPACE_ALLOWED=false
```

Then start the API from the `backend/` directory:

```bash
OPAI_LOCAL_AUTH_BYPASS=1 python main.py
```

On Windows PowerShell, use:

```powershell
$env:OPAI_LOCAL_AUTH_BYPASS = '1'
python main.py
```

The default local address is `http://localhost:8000`. Useful endpoints:

- **Swagger UI:** `http://localhost:8000/docs`
- **Health check:** `http://localhost:8000/v1/health`
- **System health:** `http://localhost:8000/v1/system/health`

The database schema is initialized at startup. Without a `DATABASE_URL`, the application uses a local SQLite database at `backend/opa.db` when started from this directory.

### 3. Start the frontend

In a second terminal, from the repository root:

```bash
cd frontend
python -m http.server 5500
```

Open **`http://localhost:5500/landing.html`**. This project does not include a `frontend/index.html`; the Vercel configuration rewrites `/` to `landing.html` in deployed static hosting.

When both services run locally, the frontend defaults to `http://localhost:8000` for its API base. If you deploy the backend elsewhere, set the frontend's `opa_api_base` browser local-storage key to the backend's base URL on the frontend origin, or update the app's configured default.

Local development opens directly into one local demo workspace; the sign-in page is paused. The no-login API bypass works only for requests from this computer and only while `OPAI_LOCAL_AUTH_BYPASS=1` is set for the backend process. Keep it disabled in deployments.

## Configuration

The full starter template is in [`backend/.env.example`](backend/.env.example). The most useful variables are:

| Variable | Purpose | Default / notes |
|---|---|---|
| `GROQ_API_KEY` | Enables Groq chat and generation. | No default; provider keys stay on the backend. |
| `GEMINI_API_KEY` | Enables Gemini reasoning and multimodal requests. | Workspace use requires paid-tier and privacy opt-in. |
| `OPENROUTER_API_KEY` | Enables OpenRouter general-chat fallback. | Private Workspace use is blocked by default. |
| `KARNA_DEFAULT_MODE` | Default mode: `auto`, `fast`, `think`, or `expert`. | `auto`. |
| `KARNA_ENABLE_FALLBACK` | Allows switching to another eligible provider. | `true`. |
| `KARNA_ENABLE_PAID_MODELS` | Enables explicitly selected paid provider models. | `false`; provider billing still follows the account plan. |
| `KARNA_GEMINI_WORKSPACE_ALLOWED` | Allows reviewed Gemini Paid-tier Workspace routing. | `false`; enable only after approving the account's data policy. |
| `KARNA_ANTHROPIC_WORKSPACE_ALLOWED` | Allows reviewed legacy Anthropic Workspace routing. | `false`; requires `KARNA_ENABLE_PAID_MODELS=true`. |
| `GROQ_MODEL` | Groq model used by automatic provider routing. | `openai/gpt-oss-120b`. |
| `GEMINI_MODEL` | Gemini model used by automatic provider routing. | `gemini-3.8-flash`. |
| `OPENROUTER_MODEL` | OpenRouter model/router used for general-chat fallback. | `openrouter/free`. |
| `DATABASE_URL` | Database connection. | `sqlite:///./opa.db`; use managed PostgreSQL or persistent storage for production. |
| `RAG_EMBEDDER` | Chooses the document embedding strategy. | `auto`; options: `auto`, `fastembed`, `hash`. |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins. | `*` in development; set explicit HTTPS origins in production. |
| `JEV_ENABLED` | Enables the optional Jev intent provider before deterministic routing fallback. | `false`. Requires the provider's endpoint and credentials. |
| `JEV_API_URL` / `JEV_API_KEY` / `JEV_MODEL` | Jev provider configuration. | Optional; see `.env.example`. |
| `KARNA_PROVIDER_LIMITS_JSON` | Optional account-specific provider RPM/TPM/RPD/TPD caps. | `{}`; add only values verified from the provider account. |
| `RAG_MAX_FILE_MB` | Maximum upload size for a RAG document. | `10` MB. |
| `GENERAL_CHAT_PER_MIN` | General chat request limit per minute. | `20`. |
| `PORT` | Port used by the backend process on hosting platforms. | `8000` locally; hosting providers usually set this. |

`ENABLE_DEV_SEED` is available for development seeding. **Keep it disabled in production.** Never commit `.env`, provider credentials, real database files, or user-uploaded documents.

## API reference

Interactive documentation is generated by FastAPI at `/docs`. The backend exposes several route groups, including:

| Area | Example routes |
|---|---|
| Health and version | `GET /v1/health`, `GET /v1/version`, `GET /v1/system/health` |
| Today and actions | `GET /v1/today`, `POST /v1/today/act`, `/v1/actions/*` |
| Core workspace | `/v1/profile`, `/v1/applications`, `/v1/opportunities`, `/v1/projects`, `/v1/academics`, `/v1/contacts`, `/v1/outreach`, `/v1/requests`, `/v1/outbox` |
| Planning and briefs | `/v1/plan/*`, `/v1/study-plans/*`, `/v1/study-blocks/*`, `/v1/briefs/*` |
| Learning | `/v1/dsa/*`, `/v1/quizzes/*`, `/v1/mastery` |
| Resume Lab | `/v1/resume-lab/*` |
| Knowledge and RAG | `/v1/rag/docs`, `/v1/rag/notes`, `/v1/rag/ask`, `/v1/rag/reindex-docs` |
| Syllabus and timetable tools | `/syllabus/*`, `/analyze`, `/refine`, `/confirm` (check `/docs` for router-specific request schemas) |

These examples are a map, not an exhaustive API contract. Use the live `/docs` output for request models, response shapes, and the complete route list for the running version.

## Database and persistence

- **Local development:** SQLite is the zero-service default.
- **Production:** prefer managed PostgreSQL or attach a persistent disk to the backend service.
- **Embeddings:** PostgreSQL `pgvector` is not required; the current retrieval path performs similarity work in Python.

Example PostgreSQL configuration:

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE
```

A SQLite file on an ephemeral hosting filesystem can disappear after a redeploy or restart. Do not rely on an ephemeral filesystem for user accounts, documents, or progress data.

### Shared directory and personal workspace

- `backend/IIT_Faculty_Dataset.csv` is the shared, read-only IIT faculty directory. Search uses this shared reference data for every account.
- Selecting a professor creates a `contacts` row owned by that user (`owner_user_id`). The same professor can be selected by several users, but each account gets its own contact record, notes, verification state, drafts, and outreach history.
- Uploaded document chunks and original files are scoped by `user_id`; RAG retrieval filters by the authenticated account before ranking results. KARNA's full-page history and popup history are stored under the user's account key in browser storage.
- Legacy shared contact rows are split by their user-specific references during database startup. When a legacy row was used by several accounts, the migration copies only professor-identifying fields and resets ambiguous private fields; any remaining unowned row is scrubbed and hidden from user APIs.

## Deployment

### Frontend — Vercel

1. Import the repository into Vercel.
2. Set the project **Root Directory** to `frontend`.
3. Use the **Other** framework preset; no build command is required for this static frontend.
4. Deploy and confirm the homepage resolves to `landing.html` through `frontend/vercel.json`.
5. Configure the deployed backend URL in the frontend if it differs from the default.

### Backend — Render or another persistent host

1. Create a Web Service for the repository and set its **Root Directory** to `backend`.
2. Build command: `pip install -r requirements.txt`.
3. Start command: `python main.py`.
4. Add your chosen provider API keys, KARNA privacy settings, and production `DATABASE_URL` in the host environment.
5. Set `CORS_ORIGINS` to the exact frontend origin(s), for example `https://opai.live,https://www.opai.live` if both are in use.
6. Use a persistent database/storage option and verify `/v1/health` after deployment.

The backend should run as a persistent Python web service, not as a static site. Provider-specific port, storage, timeout, and sleep behavior can vary, so verify those settings for your host.

## Authentication and provider setup

The frontend includes Firebase Authentication wiring for Google sign-in and email/password sign-in. Before deploying your own instance:

1. Sign-in is paused in this build. Firebase sign-in can be rebuilt later; the current local workspace does not require Firebase.
2. Enable the sign-in providers you intend to support in Firebase Authentication.
3. Add local and deployed frontend hostnames to Firebase's authorized domains.
4. Test sign-in, sign-out, account separation, and backend synchronization in the deployed environment.

Gmail sending is a separate, consented flow that requests the Gmail send scope. Configure and test the corresponding Google OAuth consent and access settings before relying on it. Do not assume that enabling Google sign-in alone grants Gmail sending access.

## Development and tests

Backend tests live in `backend/tests/`. Run them from the backend directory:

```bash
cd backend
python -m pip install pytest
python -m pytest tests -q
```

A focused deployment diagnostic script is available at `backend/scripts/check_deploy.py`; inspect its usage with:

```bash
python scripts/check_deploy.py --help
```

For provider privacy, quotas, analytics, and rollout steps, see [`backend/KARNA_MULTI_PROVIDER.md`](backend/KARNA_MULTI_PROVIDER.md). For architecture details, see [`ARCHITECTURE.md`](ARCHITECTURE.md), `STABILITY_NOTES.md`, `MERGE_NOTES.md`, and the versioned changelog files.

## Security, privacy, and launch readiness

OPAI can process resumes, academic records, personal notes, contact details, and application history. Treat the database, uploaded documents, environment variables, logs, browser storage, and repository history as sensitive.

`AuthGuard` verifies Firebase ID tokens and ties the request to the account matched from the verified email. The default mode is `enforce` on Render and when `OPAI_ENV=production`, and `log` in local development. Keep `OPAI_AUTH_MODE` away from `off` in deployments. The client still sends `user_id` for routing; it must match the identity from the verified token.

Before any public deployment:

- Keep the deployed Firebase project and authorized frontend domains aligned with the backend token verifier.
- Exercise cross-account checks for professor selections, chat, file downloads, and RAG retrieval before onboarding users.
- Configure exact HTTPS `CORS_ORIGINS` for the deployed frontend. CORS is not authorization and cannot replace backend access controls.
- Configure PostgreSQL or a verified persistent volume, then test backup, restore, and persistence across a redeploy/restart.
- Never commit API secrets, private database credentials, real resumes, academic records, uploads, or generated databases.
- Inspect both the current source tree and Git history before publishing. Removing a private file from the latest tree does not erase historical copies.
- Keep consequential actions behind server-enforced approval and verify that the exact approved payload is what executes.
- Make privacy, retention/deletion, and guest/demo claims consistent with the actual deployed data flow.

See [`SECURITY_MVP_AUDIT.md`](SECURITY_MVP_AUDIT.md) for the source-level findings, limitations, and launch checklist. The review is not a penetration test or a production security certification.

## MVP validation rule

- If users cannot complete the core task, fix or simplify the workflow first.
- If users complete it but do not return, rethink the value proposition or end-to-end workflow before adding features.
- If repeat usage is evident, prioritize the most-requested refinement.

An MVP is the smallest reliable experience that delivers the core user value—not the longest feature list.

## Contributing

Contributions and issue reports are welcome. For a change:

```bash
git checkout -b feat/short-description
# make and test your change
git add .
git commit -m "feat: describe the change"
git push -u origin feat/short-description
```

Open a pull request with the motivation, behavior change, configuration requirements, and tests performed. Please avoid committing credentials, private datasets, personal documents, or generated database files.

## License

No `LICENSE` file is present in this repository at the time this README was written. Until a license is added, do not assume the code is available for unrestricted reuse.

## Creators

OPAI is being built with a focus on useful personal AI, thoughtful product design, and reliable agentic workflows.

- **Tiru Venkatesh — Engineering & AI**  
  JNTUK UCEN. Focused on building OPAI's AI systems, retrieval-augmented generation (RAG), agent workflows, and full-stack implementation.

- **Himesh — Product Management**  
  IIT (ISM). Focused on product direction, user needs, feature prioritization, and shaping OPAI into a cohesive personal operating agent.

Together, the goal is to turn scattered tasks, context, and workflows into one useful operating layer—with people staying in control of important actions.

<p align="center"><strong>Less time managing tools. More time moving forward.</strong></p>
