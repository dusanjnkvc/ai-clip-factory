# Architecture

The application has a default free browser-hosted edition and an optional native local-server edition. Both use manual clip choices and supplied campaign/subtitle evidence. Neither pretends to perform AI analysis without a model.

## Browser edition on GitHub Pages

Next.js builds a static export using `NEXT_PUBLIC_BROWSER_MODE=true` and the repository base path. GitHub Pages serves application JavaScript, CSS, and bundled FFmpeg WebAssembly assets. It does not execute FastAPI, PostgreSQL, Python workers, or secret-bearing OAuth requests.

The browser adapter stores campaign/source/clip records and media in IndexedDB for the current origin/profile/device. Source selection does not upload videos to GitHub. FFmpeg WebAssembly runs on the visitor’s CPU and renders the selected source range/crop with optional supplied caption cues. The UI requires no login or API key. Project code is public in the dedicated Pages repository; users’ browser records are not repository files.

A browser queue is tied to the open tab. It cannot offer durable worker leases/recovery after closure, cross-device sync, or cloud backup. Reloading or closing can interrupt renders; storage eviction/clearing can lose data. Browser CPU/memory limits differ from native FFmpeg. Local no-service-fee operation still uses the visitor’s electricity, device, storage, and internet.

## Optional native local edition

The same frontend can use a same-origin `/api` path forwarded to FastAPI. The API persists owner-scoped campaign/source/rights records and durable jobs. A separate Python CPU worker renders real clips outside web requests. SQLite/local disk support desktop use; optional local Docker uses PostgreSQL and shared media volumes.

The free nonproduction workspace opens without a login and remains bound to loopback. That convenience is not an unauthenticated public-server security model. A public native backend needs deliberate authentication/administration and infrastructure/cost review.

`FREE_MODE=true` selects the local manual service and blocks hosted AI, S3 operations, and direct external publishing even if credentials exist. No language model or GPU is installed. Users supply source ranges, crop, metadata, and optional SRT/VTT. Conservative campaign parsing copies only explicit recognizable patterns and flags review. Cue timestamps are retained exactly; missing captions do not become fabricated transcripts or word timings.

Native FFmpeg validates container magic, forces demuxers, restricts input protocols, trims/crops to vertical output, applies captions, normalizes audio, and encodes H.264/AAC. Plans record user choices and provenance. Versions/compliance results are committed independently. The browser polls actual persisted native state rather than timed demonstrations. Database leases support native crash recovery; distributed operation remains an operational validation task.

## Shared evidence and review boundaries

Media rights attestations, editing decisions, deterministic format/duration/tag checks, and human semantic review remain distinct. Source rights, content context, branding, disclosures, audio restrictions, and draft approval need meaningful evidence. Public URLs do not establish reuse permission.

A render is not publication; publication is not confirmed campaign submission. Manual records use actual public URLs and timestamps, and countdowns derive from those times. Financial summaries distinguish estimates, confirmed amounts, received payouts, and reported expenses. No view count or monetary charge is invented.

Temporary render files are cleaned where supported. A configured native retention value does not authorize deleting permanent originals/versions automatically. Browser IndexedDB may be cleared by the browser or user, so keep originals and downloaded results outside the app.

## Optional external adapters

Hosted AI, sampled cloud vision, official YouTube upload, and S3 remain source-level optional native adapters behind explicit `FREE_MODE=false`, credentials, spending checks, and authorization. They are absent from the static browser execution path and can incur costs. Their presence does not establish a free tier, live provider permission, successful publication, or cloud deployment.
