# AI Clip Factory

A free, manual clipping workspace with **no login, paid AI API, or subscription requirement**. The GitHub Pages edition stores your videos and project records in your browser and renders clips there with FFmpeg WebAssembly. It needs no Python server, cloud worker, OpenAI key, or local AI model.

The workflow uses manual clip selection/review, optional supplied SRT/VTT subtitles, and user-authored metadata. It does not claim AI transcription, best-moment detection, semantic video understanding, or viral scoring. Your existing device, electricity, disk, and internet are still needed. See [implementation status](docs/STATUS.md) for verification and limitations. This project is separate from LogEN.

## Open the browser edition

After the dedicated GitHub repository’s Pages deployment succeeds, open its published Pages URL. **A configured workflow is not proof that the site is already deployed**; the final delivery supplies the actual verified address or any remaining setup.

No account or API key is required:

1. Add a campaign brief and review its rules. The local parser can copy obvious, explicitly supplied requirements; correct missing or ambiguous fields yourself.
2. Choose a video you own or are authorized to edit and republish, and record the rights evidence.
3. Set the source start/end, crop, subtitle style, title, and description. A blank end uses up to 30 available seconds from your start; this is a default range, not a detected highlight.
4. Optionally supply an SRT/VTT file with cue times relative to the original source. Without that file, the free workflow does not transcribe speech or invent captions.
5. Keep the tab open while FFmpeg renders. Preview the real MP4, review compliance, and download the clip/upload package.
6. Publish manually through your authorized platform account. Record the actual public URL and publication time, then complete the campaign submission separately.

## Where browser data lives

Videos, clips, and project records stay in **IndexedDB in the current browser profile on this device**. Choosing a video does not upload it to GitHub or the repository. The site downloads its app/FFmpeg assets; media rendering happens on your device. GitHub hosts public application files, not a private video-processing backend.

Clearing this site’s browser storage, changing browser/profile/device, using private browsing, or browser storage eviction can remove or make records unavailable. Download important outputs and preserve your originals elsewhere. There is no cross-device sync, account recovery, or automatic cloud backup. Anyone with access to the same browser profile may access its local records.

The browser renderer needs available memory and CPU. Large/high-resolution sources can exceed browser limits or be slow; use shorter source files when necessary. Keep the tab open. Closing/reloading during a render can interrupt it: this browser queue is not a durable cloud worker. No runtime or publish-ready guarantee follows from a successful short fixture.

## GitHub Pages hosting

The dedicated repository is [dusanjnkvc/ai-clip-factory](https://github.com/dusanjnkvc/ai-clip-factory).

The chosen free hosting path uses a **public repository** named `ai-clip-factory`. Its application source is public. Secrets, `.env`, uploaded media, local databases, build outputs, and browser data must stay out of Git. A public source repository does not publish your browser’s IndexedDB videos.

The Pages workflow builds a static Next.js export with `NEXT_PUBLIC_BROWSER_MODE=true` and `NEXT_PUBLIC_BASE_PATH=/ai-clip-factory`, includes the local FFmpeg assets, and deploys `frontend/out`. In the repository’s **Settings → Pages**, select **GitHub Actions** as the build/deployment source if it is not already set. The final URL is available only after a successful deployment.

To reproduce its static build locally, run `npm ci`, `node --test scripts/test-browser.mjs`, and `npm run build:pages` from `frontend/`. Preparation copies the single-thread FFmpeg core and worker modules and packages the caption font for same-origin loading. Notices are included in `ffmpeg/LICENSES.txt` and `ffmpeg/FONT-LICENSE.txt`; FFmpeg core uses GPL-2.0-or-later and Noto Sans uses SIL OFL 1.1.

If repository creation/connection is still needed, create an empty public `ai-clip-factory` repository under `dusanjnkvc`, without an initialized README/license/gitignore, then run from this checkout:

```sh
git remote add origin https://github.com/dusanjnkvc/ai-clip-factory.git
git push -u origin main
```

For an installed, authenticated GitHub CLI:

```sh
gh repo create dusanjnkvc/ai-clip-factory --public --source . --remote origin --push
```

Use these commands only when the matching repository/remote does not already exist. Inspect `git status` before pushing. Pages service quotas/availability apply; the application does not configure paid AI or a billable server. See [deployment notes](docs/DEPLOYMENT.md).

## Optional local Python edition

The local server edition remains available for native FFmpeg and a persistent local database/worker. Its free development configuration opens a local workspace without a login. Use it when browser memory or performance is unsuitable.

For this prepared checkout, keep `FREE_MODE=true`, leave cloud credentials blank, and run:

```powershell
.\scripts\dev.ps1
```

Open [localhost:3000](http://localhost:3000). The launcher loads `.env` as data, applies migrations, starts the API and worker, and serves Next.js. Logs are in ignored `.runtime/`; Ctrl+C stops the processes.

For a clean checkout, install Node.js 22 or later and Python 3.12:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Push-Location frontend
npm.cmd ci
Pop-Location
Copy-Item .env.example .env
```

Use a random `APP_SECRET` of at least 32 characters, keep `FREE_MODE=true`, and leave `OPENAI_API_KEY=` blank. The Python packages include an FFmpeg fallback on supported Windows systems; installed FFmpeg/ffprobe with libass and libx264 is also supported. No AI model is downloaded. Pass `-Python 'C:\path\python.exe'` to the launcher if necessary.

Optional local Docker/Compose runs PostgreSQL and the native CPU worker on your computer. Replace `POSTGRES_PASSWORD` with a random value before `docker compose up -d --build`. Docker is not required for the browser edition; its licensing depends on your use. Container volumes retain local records/media until explicitly removed.

## No paid services by default

In the native edition, `FREE_MODE=true` is the default even when no variable is supplied. It blocks hosted AI, external S3 operations, and direct social publishing even if old credentials exist. Local files, manual metadata, compliance review, packages, recorded URLs, manual submissions, and explicit analytics imports remain available.

Optional hosted adapters remain in the source. They need explicit `FREE_MODE=false`, credentials, positive spending limits, and user authorization, and can incur charges. They are not part of the browser edition or selected free workflow. A public backend deployment would need its own security, authentication, infrastructure, and cost review.

## Validation and benchmarks

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m pytest -q
Pop-Location
Push-Location frontend
npm.cmd run build
Pop-Location
```

The original hosted-adapter MVP had 46 passing backend tests. That historical result does not verify later free/browser changes; current test/build/browser results are recorded in the final delivery and [status](docs/STATUS.md). Technical render fixtures use generated video/audio without third-party footage. No unit test establishes live social permissions, campaign approval, earnings, or a cloud deployment.

The [native benchmark](docs/BENCHMARK.md) uses the optional local API/worker and is separate from browser rendering. It defaults to one manual range and refuses hosted jobs unless explicitly allowed. Browser renders must be measured in the actual browser/device with the tab open; do not reuse native-worker timings as browser results.

## Real performance and financial records

Where the selected edition exposes imports, use a UTF-8 views CSV with `post_url,reported_views,eligible_views,likes,shares`; only the first two columns are required. URLs must already be recorded. Eligible views cannot exceed reported views, and reported views do not establish payment eligibility.

Financial records need actual report/invoice evidence. Estimated earnings, confirmed amounts, received payouts, and reported expenses remain distinct. Records are additive, so enter an amount once. USD summaries do not convert other currencies. Local processing does not create an invented paid-provider charge.
