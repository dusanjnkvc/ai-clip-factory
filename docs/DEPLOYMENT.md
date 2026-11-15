# Cloud deployment

The web server, API, and FFmpeg worker need separate processes. A request-based serverless host alone cannot run this pipeline reliably. The included containers can run on a small Linux VM or a container platform with persistent storage and long-running CPU workers.

## Single-VM deployment

Use a Linux VM with Docker Compose v2. Start with 2–4 CPU cores and 4–8 GB RAM and adjust after benchmarking representative media. These are starting configurations, not measured capacity or cost guarantees. Allow free space for source media, audio extracts, render outputs, and database backups. No GPU is required.

1. Clone the dedicated `ai-clip-factory` repository. Copy `.env.example` to `.env` on the server; never add the filled-in file to Git.
2. Generate strong, different `APP_SECRET` and URL-safe `POSTGRES_PASSWORD` values. Set `APP_ENV=production`.
3. Point your domain's DNS at the server. Set `DOMAIN=clips.example.com`, `PUBLIC_URL=https://clips.example.com`, `FRONTEND_URL=https://clips.example.com`, and `API_BASE_URL=https://clips.example.com` in `.env`.
4. Add the hosted AI key and configure model/budget limits. Keep provider billing limits enabled as a second control.
5. Open inbound TCP 80/443 and UDP 443 for HTTPS; restrict SSH to your administration network. PostgreSQL and the API remain on the internal Compose network. The base frontend port is bound to loopback.
6. Start the HTTPS overlay:

```sh
docker compose -f docker-compose.yml -f docker-compose.production.yml up -d --build
docker compose logs -f migrate api worker caddy
```

Caddy obtains HTTPS certificates for the configured domain. Production sessions require HTTPS. A healthy API and a running worker are both required; the health endpoint does not prove hosted AI authorization or verify a rendering benchmark.

## Configuration and secrets

Use your cloud's secret manager or a protected server `.env` with access limited to the deployment user. Configure `OPENAI_BASE_URL`, `AI_MODEL`, and `TRANSCRIPTION_MODEL` for a compatible hosted provider. Do not route AI requests through the browser or embed credentials in Next.js public environment variables.

`whisper-1` supplies word timestamps for the implemented subtitle workflow. The provider documents its deprecation for February 26, 2027. Revalidate timestamp support and run transcript synchronization tests before changing to a replacement. See [the official speech-to-text guide](https://developers.openai.com/api/docs/guides/speech-to-text).

For YouTube, create a Google Cloud OAuth web client, enable the YouTube Data API, configure its consent screen/scopes, and set the exact HTTPS callback `https://clips.example.com/api/accounts/youtube/callback`. Supply `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, and `YOUTUBE_REDIRECT_URI`. Generate `TOKEN_ENCRYPTION_KEY` with:

```sh
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Store that key securely and retain it across upgrades; losing it prevents decryption of saved platform tokens. Google may restrict uploads from unverified projects. [YouTube's upload documentation](https://developers.google.com/youtube/v3/docs/videos/insert) describes project verification and upload permissions. Connecting an account does not authorize unattended publication of every future clip.

TikTok and Instagram require eligible accounts and approved official API access. Until an integration is configured and implemented, use the application's download/manual publication workflow. Content Rewards submissions remain manual unless a real authorized integration is available.

## Persistent data and operations

The default deployment stores PostgreSQL in `postgres_data` and authorized source/generated files in `media_data`. Back up both. Encrypt cloud disks and backups. Set retention according to the campaign's requirements and your users' expectations. Check the implementation status before relying on automatic retention cleanup.

To back up PostgreSQL without placing its password in command history:

```sh
docker compose exec -T db pg_dump -U clipfactory -d clipfactory -Fc > clipfactory.dump
```

Place the resulting backup outside the source repository. Back up the media volume separately using your cloud volume snapshot service. Periodically restore into an isolated environment and verify a source and clip can be retrieved by their owner.

S3-compatible configuration is available for object transfer where supported. The worker still needs temporary disk. Multiple workers need access to the same source objects; the single-VM shared volume is the simplest supported topology. Do not scale to separate hosts until shared object storage, leases, and atomic claim behavior have been checked on that topology.

On upgrade, back up first, pull a reviewed commit, and rerun Compose with `--build`. The migration service applies database changes before workers/API restart. Monitor job errors, overdue leases, worker restarts, storage use, provider costs, and submission deadlines. Configure cloud alerts outside the application for machine availability and billing.

## Verification before real campaigns

Complete one credentialed round trip with authorized sample media: campaign import, provider analysis, transcript, real rendered MP4, metadata, compliance review, owner-only download, and a permitted private YouTube upload if configured. Confirm the returned post URL and actual timestamp, then confirm the manual submission state. Record the measured first-clip latency using the benchmark guide.

This repository includes deployment configuration. It does not establish a provisioned cloud account, live domain, API access, successful cloud deployment, or tested live social publication.
