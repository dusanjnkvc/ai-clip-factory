# Free browser hosting and optional local operation

## GitHub Pages edition

The selected hosted edition is a static site. Next.js exports application files; FFmpeg WebAssembly renders on the visitor’s device; IndexedDB stores the visitor’s local records/media. GitHub Pages does not run Python, PostgreSQL, FFmpeg CPU workers, OAuth secrets, or a media-upload server.

The [live browser app](https://dusanjnkvc.github.io/ai-clip-factory/) is published from [dusanjnkvc/ai-clip-factory](https://github.com/dusanjnkvc/ai-clip-factory). The initial Pages deployment was verified. Each subsequent change still needs its own successful deployment before it appears at the live URL.

Use the dedicated **public** `ai-clip-factory` repository for the selected free Pages path. Application code becomes public. `.env`, tokens, source videos, rendered user media, databases, and runtime files remain excluded by `.gitignore`; browser IndexedDB is not committed to Git. Existing LogEN source/repositories are outside this project.

The deployment workflow uses:

- `NEXT_PUBLIC_BROWSER_MODE=true`
- `NEXT_PUBLIC_BASE_PATH=/ai-clip-factory`
- Next.js static output in `frontend/out`
- Bundled FFmpeg JavaScript/WebAssembly assets copied into the static output
- GitHub Actions Pages artifact upload/deployment

In repository **Settings → Pages**, choose **GitHub Actions** as the deployment source. Push the reviewed source and wait for the Pages deployment to finish. Use its returned/verified URL. A workflow file, static build, or repository push alone is not proof of successful hosting. A failed or pending deployment must be reported honestly.

This repository is already configured for GitHub Actions Pages. Do not create a second repository or change the origin merely to publish an update.

There is no account/login, API signup, or application subscription in this edition. It does not configure a billable backend or paid AI. GitHub’s hosting quotas and availability still apply. The visitor uses their own device resources and internet connection; unlimited runtime, storage, availability, or perpetual service cannot be promised.

## Browser data and runtime limits

IndexedDB is scoped to a browser profile/device and site origin. Clearing site data, browser eviction, private browsing expiry, changing profiles/devices, or changing the site origin can remove or hide local data. There is no cloud sync or account recovery. Preserve source originals and download important results outside the browser.

The app and FFmpeg assets are served as static files. Selecting a source video stores it locally rather than sending it to GitHub for processing. GitHub receives normal site/asset requests; it is not a private video storage service.

Keep the tab open during rendering. Closing/reloading can interrupt a job; a browser queue does not provide the durable lease/recovery behavior of the optional native worker. Browser memory and CPU limits can reject large media. Start with short authorized sources and measure the actual target devices. Captions require supplied source-timed SRT/VTT; no speech recognition or local AI model is installed.

Creative Director also runs entirely in this browser edition. Its frame/audio measurements, assisted concepts, drafts, and actual FFmpeg renders need no server route or secret. A semantic AI provider is not configured. The optional native edition does not provide the Director project/analyzer interface; use the published browser edition for that feature. See the [Creative Director guide](CREATIVE_DIRECTOR.md).

## Optional native local edition

For stronger native FFmpeg performance, run the Windows launcher from README with `FREE_MODE=true`. It uses a local FastAPI service, SQLite/local disk, and a separate persistent worker. The free development workspace does not need a login. Keep services bound to loopback; this local convenience is not appropriate as an unauthenticated public backend.

Docker/Compose is optional and runs the API, PostgreSQL, worker, and Next.js on the existing computer. It has no cloud hosting requirement. Use random application/database secrets and retain database/media volumes. Check Docker licensing for your own use. Electricity, hardware, disk, and internet are still resources.

The supplied cloud/HTTPS container overlay is retained as an optional architecture artifact. Publishing a native backend publicly requires deliberate authentication/security configuration and a cost review. It is outside the selected free Pages deployment and has not been verified as a provisioned cloud service.

## Optional external adapters

Native hosted AI, official YouTube publishing, and S3 adapters are disabled by `FREE_MODE=true`. A saved key cannot override that guard. Enabling them requires explicit `FREE_MODE=false`, credentials, positive spending limits, account eligibility, and authorization. It can incur charges; do not enable it for the no-paid-services workflow.

Free mode uses manual platform upload packages and manual Content Rewards submission. A rendered file is not a published post, and publication is not confirmed submission. Record actual public URLs and timestamps and verify campaign-specific deadlines yourself.

## Verification

The final delivery records static build/browser checks, actual rendering checks, repository creation, and Pages deployment status separately. No hosted AI request, social upload, financial result, or successful deployment is inferred from unit tests. Native and browser rendering have different performance characteristics and must be measured independently.
