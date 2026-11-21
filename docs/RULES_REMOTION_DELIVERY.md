# Rules, Remotion and first-time account setup

Update: November21,2026. Extends the existing AI Clip Factory repository and preserves source videos, old clips, projects, campaign records, models and analytics. No LogEN files were touched.

## Visible rules and mandatory precedence

Create Clips exposes text/PDF input directly. The native form no longer hides it in a closed disclosure. The online browser form also accepts PDF/TXT. PDF.js reads text-based PDFs on the user's device, retaining the attachment and extracted wording; recognized requirements cite the source filename. Scanned/image-only PDFs explicitly need pasted text or OCR rather than silently dropping rules. Text extraction is bounded to80 pages,15MB and100,000 characters. No PDF JavaScript/actions are executed.

Required hashtags keep their campaign order, then required @mentions appear before the rest of the publication text. Optional tags follow the mandatory tag list. This precedence is applied to generated metadata, manual metadata saves and the actual render job. Other manual body text is preserved. Required on-screen wording is attached to every clip's render plan and displayed for the video duration; saving an edit cannot silently remove it. Long wording that cannot fit a readable overlay fails for review instead of being truncated. Semantic correctness/readability still require actual video review. Common explicit labels are recognized online; natural instructions with quoted on-screen wording are also supported conservatively. The native edition retains its additional local-model extraction and source-quote checks.

## Real Remotion editing

Remotion packages are pinned together at4.0.545. The shared composition renders the on-video headline, exact mandatory wording, supplied/transcribed timed captions and text overlays. The existing validated FFmpeg timeline prepares cuts, effects, source framing and normalized audio; Remotion produces the final MP4. This retains the existing processing capabilities while adding a real React video composition rather than a decorative button.

The free online edition uses `@remotion/web-renderer` on the device, with H.264/AAC capability checks, bounded media cache, progress and final FFmpeg probe/full decode verification. A free FFmpeg compatibility mode remains available. No Lambda, paid rendering server or hosted AI key is required. Keep the tab open; supported browser codecs, available memory, existing device and internet for loading assets remain practical limits. Source/output media is stored in the browser's existing IndexedDB. Remotion sends its documented usage telemetry, not video uploads to a rendering service.

The native edition uses a local Node bridge with one Chromium render at a time and a cached bundle. The source is served only over an ephemeral loopback URL with an unguessable token, and that server is closed after the render. It requires installed frontend dependencies/Node and may download the official headless browser on first use. The original source is never overwritten. Base video and actual output are versioned; Remotion Player previews the same clean base/composition. Metadata-only saves continue reusing video. Legacy FFmpeg outputs remain accessible and obtain a clean Remotion base after a Remotion edit. Native container images do not automatically provide a separate Node rendering service; use the documented Node/local setup or browser rendering for Remotion.

Remotion is free for individuals and eligible entities up to three people under its Free License. Larger organizations have different licensing. No paid Remotion key is configured. See [third-party terms](../THIRD_PARTY_LICENSES.md).

## YouTube/TikTok setup

The user confirmed that no registered developer apps exist. Settings now includes three guided steps: register app, configure callback/scopes, authorize account. Google instructions cover enabling the Data/Analytics APIs, consent-screen test users and a Web OAuth client. TikTok instructions cover Login Kit/Display API, accepted HTTPS callbacks and separately approved posting/statistics scopes.

The native development wizard securely saves app settings encrypted outside the media serving root, generates/preserves the token-encryption key, enables the separate social feature switch and refreshes connection diagnostics. It never returns client secrets. Production rejects the setup-write route; deployment operators must manage its secrets. Official OAuth state/PKCE, token handling and posting checks are retained. The worker reads the same saved settings. Controlled tests verify encrypted persistence and generation of the official Google authorization URL without leaking secrets.

GitHub Pages is static hosting and cannot hold client secrets or exchange secret-based OAuth codes. Its setup flow says this clearly and never presents a fake connected account. Use the configured native backend or a properly secured HTTPS backend for connection, or download the package and publish manually. Do not expose the no-login local backend through a public tunnel. Actual Google/TikTok authorization and posting remain untested because the owner's developer apps/approved permissions are not yet available. No supplied footage was posted. See [setup details](SOCIAL_SETUP.md).

## Actual verification and artifacts

A generated synthetic3s source and owned rules PDF were used, with no third-party media rights claim. The browser UI uploaded the PDF and source, then generated a1.8s1080×1920,30FPS H.264/AAC MP4 through Remotion. Its metadata begins `#CampaignFirst #Second @requiredcreator @requiredbrand`, followed by the exact retained description. Optional `#Optional` follows the required tag array. Decoded output pixels visibly contain `EXACT CAMPAIGN WORDING`. This is real rendering acceptance, not gaming/AI quality validation.

Browser output: `C:\Users\duled\Downloads\clip-f417bffd.mp4`.

Local evidence under ignored `.runtime/remotion-acceptance/`:

- `source.mp4`, `rules.pdf`: owned test inputs.
- `remotion.mp4`, `result.json`: actual native Node/Remotion output and full decode measurements.
- `rendered-frame.jpg`: native output with required text and captions visibly rendered.
- `browser-rendered-frame.jpg`: actual browser MP4 frame with the PDF's exact mandatory wording.

Native Remotion output measured1.81s,1080×1920,H.264/AAC and passed full decode. Browser output independently measured1.81s,1080×1920,30FPS,H.264/AAC. Remotion Studio was opened before composition development; the same composition is used by the app's Player and both render paths. A browser edit is rerendered as a new version with requirements retained.

Local validation:225 backend checks; 61 browser rules/API/creative and real WASM checks passed. TypeScript, native production and GitHub Pages static builds passed. Remotion version alignment passed and npm audit reported zero known vulnerabilities. Controlled integration tests do not claim live platform approval, connection or publication. Professional highlight-selection limitations from the preceding [redesign report](REDESIGN_DELIVERY.md) remain.

The browser editor was also exercised end to end: changing the headline created v2, while retaining the exact required on-screen wording, campaign-first tags/mentions and the manual description. The actual edited export is `C:\Users\duled\Downloads\clip-f417bffd (1).mp4`. UI proof is saved as `.runtime/remotion-acceptance/editor-verified.jpg`. Account registration steps were inspected without inventing developer credentials or sending real authorization requests.
