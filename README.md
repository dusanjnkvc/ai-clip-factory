# AI Clip Factory

A Next.js and FastAPI application for turning authorized source media and campaign requirements into vertical clips. Video processing runs in a separate CPU worker using FFmpeg and hosted AI; no local language model or GPU is required.

This checkout is independent of LogEN. It does not contain credentials or an existing deployment. See [implementation status](docs/STATUS.md) for verified features, external setup requirements, and remaining limitations.

## Start with Docker

Requirements: Docker Engine/Desktop with Compose v2 and a hosted AI API key for automatic generation.

1. Copy `.env.example` to `.env`.
2. Replace `APP_SECRET` with a random secret of at least 32 characters and `POSTGRES_PASSWORD` with a random URL-safe password. Set `OPENAI_API_KEY`. The optional YouTube and S3 settings can remain blank.
3. Start the stack:

```sh
docker compose up -d --build
docker compose logs -f api worker
```

Open [localhost:3000](http://localhost:3000), create an account, and add a campaign brief. Upload a video that you own or are authorized to reuse, confirm its rights, and choose **Generate FAST**. The first clip becomes available independently while later clips continue processing. Every clip retains its campaign rules and compliance results.

The database migration runs before the API and worker start. PostgreSQL and media persist in Docker volumes. `docker compose down` preserves those volumes; deleting them removes stored records and media.

Without an AI key you can inspect the dashboard and save records, but automatic campaign analysis, transcription, and clip creation report missing configuration. Processing progress represents persisted work, not a timed demonstration. Official platform credentials and explicit approval are required for publishing.

## Start on Windows without Docker

Install Node.js 22 or later, Python 3.12, and FFmpeg/ffprobe with libass and libx264. From the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Push-Location frontend
npm.cmd ci
Pop-Location
Copy-Item .env.example .env
```

Edit `.env` as described above, then run:

```powershell
.\scripts\dev.ps1
```

The script loads `.env` as data, applies migrations, starts the API and worker, and serves the frontend. API/worker logs are in ignored `.runtime/`. Press Ctrl+C to stop. If your Python executable has a different path, pass `-Python 'C:\path\python.exe'`.

For separate terminals, load your `.env` settings into each terminal, then run `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000` and `python -m app.worker` from `backend/`, and `npm run dev` from `frontend/`. Run `python -m alembic upgrade head` in `backend/` before the first start. API documentation is at [localhost:8000/docs](http://localhost:8000/docs).

## Validation

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m pytest -q
Pop-Location
Push-Location frontend
npm.cmd run build
Pop-Location
```

The media test uses generated FFmpeg test signals, so it needs no third-party media license. Tests that use substitutes for remote AI or OAuth validate application behavior only; they do not establish that a provider or social account is authorized. Live AI generation and YouTube publishing need separate credentialed checks.

Verified locally: **46 backend tests pass**, TypeScript checks pass, and the frontend production build succeeds. Browser verification covered account creation, campaign correction, an authorized test-media upload, a real queued job, the missing-provider blocked state, and mobile navigation. See [status and MVP boundaries](docs/STATUS.md) before using real campaigns.

The local `.env` generated during development contains random application secrets and points to a fresh `ai-clip-factory.db`. Cloud credentials remain empty. `.env`, databases, test accounts, media, and build outputs are ignored by Git.

## Import performance and financial records

In **Earnings & Analytics**, use **Import views CSV** with a UTF-8 CSV containing `post_url,reported_views,eligible_views,likes,shares`. Only `post_url` and `reported_views` are required. The post URL must already be recorded in your workspace; eligible views cannot exceed reported views. Imports add dated observations and do not establish payment eligibility.

Use **Add record** for estimated earnings, confirmed earnings, an actual payout, or a reported processing expense. Supply campaign/report/invoice evidence. Financial records are additive; enter each amount once. Dashboard summaries include USD records only. Provider token usage is stored separately in the audit log and is not converted into invented dollar charges. Workspace spending reservations can be lowered in **Settings**; configure provider-side billing limits as well.

See [benchmark instructions](docs/BENCHMARK.md), [cloud deployment](docs/DEPLOYMENT.md), and [architecture](docs/ARCHITECTURE.md). GitHub Actions performs the backend tests and frontend production build.

## Connect the intended GitHub repository

GitHub access was inspected, but the available connector does not create repositories and `gh` was not installed. The project can be committed locally without changing any other repository.

Create a **private**, empty repository named `ai-clip-factory` under `dusanjnkvc` at [GitHub's new repository page](https://github.com/new). Do not initialize it with a README, license, or gitignore. From this directory:

```sh
git remote add origin https://github.com/dusanjnkvc/ai-clip-factory.git
git push -u origin main
```

If the local checkout has not yet been initialized:

```sh
git init -b main
git add .
git commit -m "Build AI Clip Factory vertical slice"
git remote add origin https://github.com/dusanjnkvc/ai-clip-factory.git
git push -u origin main
```

With an installed and authenticated GitHub CLI, `gh repo create dusanjnkvc/ai-clip-factory --private --source . --remote origin --push` creates and connects it in one step. Inspect `git status` before committing; keep `.env`, uploaded media, tokens, local databases, and `.runtime/` untracked.
