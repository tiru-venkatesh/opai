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
  <img src="https://img.shields.io/badge/AI-Groq%20%7C%20RAG-5A45FF" alt="Groq and RAG" />
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
Intent / entity routing
    │
    ├── Optional Jev provider
    ├── Groq structured decision fallback
    └── Deterministic rules fallback
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
    AG --> JE[Optional Jev decision provider]
    AG --> GROQ[Groq model APIs]
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
| AI | Groq API; optional Jev intent routing; deterministic fallbacks |
| Retrieval | FastEmbed, `BAAI/bge-small-en-v1.5`, Python-side similarity/keyword retrieval |
| Document processing | `pypdf`, `python-docx`, `python-multipart`, ReportLab for PDF export features |
| Hosting pattern | Vercel or another static host for the frontend; Render, Railway, Fly.io, or a VPS for the backend |

## Repository layout

```text
opa-main/
├── frontend/                  # Multi-page static application and landing page
│   ├── landing.html           # Public homepage entry
│   ├── login.html              # Sign-in UI
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
├── ARCHITECTURE.md             # Deeper architecture notes
├── CHANGELOG-v*.md             # Development history
└── README.md
```

## Getting started

### 1. Requirements

- Python **3.10 or newer**.
- A Groq API key for AI features that call Groq.
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

Open `backend/.env` and set your key:

```dotenv
GROQ_API_KEY=your_groq_api_key
```

Then start the API from the `backend/` directory:

```bash
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

> **Tip:** Open the frontend over `http://localhost` or HTTPS rather than opening the HTML file directly. Firebase sign-in and browser APIs may not work from a `file://` URL.

## Configuration

The full starter template is in [`backend/.env.example`](backend/.env.example). The most useful variables are:

| Variable | Purpose | Default / notes |
|---|---|---|
| `GROQ_API_KEY` | Enables Groq-backed chat and generation workflows. | No default; configure a private key. |
| `DATABASE_URL` | Database connection. | `sqlite:///./opa.db`; use managed PostgreSQL or persistent storage for production. |
| `RAG_EMBEDDER` | Chooses the document embedding strategy. | `auto`; options: `auto`, `fastembed`, `hash`. |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins. | `*` in development; set explicit HTTPS origins in production. |
| `JEV_ENABLED` | Enables the optional Jev routing provider before Groq fallback. | `false`. Requires the provider's endpoint and credentials to be configured. |
| `JEV_API_URL` / `JEV_API_KEY` / `JEV_MODEL` | Jev provider configuration. | Optional; see `.env.example`. |
| `GROQ_ROUTER_MODEL` | Model used for structured routing. | `openai/gpt-oss-20b`. |
| `GROQ_CHAT_MODEL` | Model for general chat. | `openai/gpt-oss-20b`. |
| `GROQ_AGENT_MODEL` | Model for agent/tool workflows. | `openai/gpt-oss-120b`. |
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
4. Add `GROQ_API_KEY` and your production `DATABASE_URL` in the provider's environment settings.
5. Set `CORS_ORIGINS` to the exact frontend origin(s), for example `https://opai.live,https://www.opai.live` if both are in use.
6. Use a persistent database/storage option and verify `/v1/health` after deployment.

The backend should run as a persistent Python web service, not as a static site. Provider-specific port, storage, timeout, and sleep behavior can vary, so verify those settings for your host.

## Authentication and provider setup

The frontend includes Firebase Authentication wiring for Google sign-in and email/password sign-in. Before deploying your own instance:

1. Configure the Firebase web-app settings in the frontend's Firebase configuration blocks (`frontend/app.js` and `frontend/login.html`).
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

For deeper system context, see [`ARCHITECTURE.md`](ARCHITECTURE.md), `STABILITY_NOTES.md`, `MERGE_NOTES.md`, and the versioned changelog files.

## Security and data handling

OPAI can process resumes, academic information, personal notes, and contact details. Treat the database, uploaded files, environment variables, logs, and browser storage as sensitive.

- Keep API keys and database credentials in environment variables, not frontend source or commits.
- Set restrictive `CORS_ORIGINS` values in production.
- Review access control, authorization, and deployment settings before exposing a backend publicly; a development login endpoint exists and should not be treated as production authentication by itself.
- Review uploaded or sample documents before making a repository public. **This archive currently includes PDF files under `backend/resumes/`; remove or sanitize any real people's resumes before public distribution and add that runtime-data path to `.gitignore` if it should not be versioned.**
- Avoid storing real user data in test fixtures or checked-in SQLite databases.

This README is not a security audit. Perform a deployment-specific review before handling real users' data.

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

## Creator

**Tiru Venkatesh** — building OPAI as an exploration of personal AI, retrieval-augmented generation, agentic workflows, full-stack engineering, and human-approved automation.

<p align="center"><strong>Less time managing tools. More time moving forward.</strong></p>
