# Architecture

The frontend uses Next.js, TypeScript, and Tailwind. Browser requests use the same-origin `/api` path; the Next.js server forwards them to FastAPI during development. The production Caddy configuration forwards `/api` directly to FastAPI so large source uploads bypass the frontend server. The API validates sessions and ownership, persists campaign/media records, and queues durable database jobs. It does not wait for an FFmpeg render inside the upload or generation request.

A separate Python worker claims queued work with database leases. SQLite is available for development; PostgreSQL is used by Compose. This database queue is the durable-queue equivalent for the initial implementation, so Redis is not required. Retry and crash recovery are application concerns and must be tested against the deployment database when scaling.

The media services use a configurable hosted AI endpoint for rule extraction, transcription, selection, Edit DNA, and platform metadata. Campaign rules retain evidence and uncertainty. FFmpeg decodes the source and renders the structured plan, cropping to vertical output, applying subtitles, normalizing audio, and encoding H.264/AAC. Rendering does not require a local model. Every output needs validation against its captured rules; uncertain semantic requirements remain review items.

The worker makes individual rendered clips available as it progresses. The frontend polls persisted state rather than inventing progress. Transcript and analysis reuse reduce duplicate provider work. Different source moments and edit decisions matter more than surface-level color/font changes; near-duplicate selections should be flagged rather than disguised.

Campaign extraction and media understanding involve untrusted content. Model output must pass schema and timeline validation before becoming FFmpeg arguments or compliance state. FFmpeg is launched with argument arrays, never a shell-built filter command. User filenames do not become arbitrary filesystem paths. Uploaded media remains subject to file validation, owner checks, and an explicit rights record.

Source files, editing versions, compliance evidence, publishing records, and submissions remain distinct. A rendered video is not a published video, and a publication is not a confirmed Content Rewards submission. Submission deadlines derive from the actual recorded publication timestamp. Financial summaries distinguish estimates, confirmed amounts, actual payouts, and processing expenses; missing observations remain missing.

The initial deployment is one VM with persistent volumes, PostgreSQL, an API container, a worker container, and a Next.js container. Caddy adds HTTPS. Optional object storage is separate from temporary worker files. More advanced subject tracking, provider adapters, platform adapters, and distributed rendering can build on the service boundaries after the vertical slice is validated with real media and credentials.
