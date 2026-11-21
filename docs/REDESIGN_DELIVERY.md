# Unified creation redesign — delivery evidence

Date: November 20, 2026. Repository: `dusanjnkvc/ai-clip-factory`, branch `codex/unified-creation`. This extends the existing application. Local originals, saved campaigns, earlier clips, models, public-post records and analytics were preserved. LogEN was not accessed or changed.

## Implemented workflow

- Five main navigation sections: Create Clips, Generated Clips, Video Library, Analytics, Settings. Native creation opens directly without login. Browser edition keeps manual clipping and optional measured concepts inside Create Clips, with saved campaign/publication records accessible from Settings.
- Native source upload, library selection or optional authorized public YouTube URL; optional PDF/TXT/DOCX/pasted/saved campaign rules; count1/2/3/5/custom1–10; duration10/15/20/30/45/60/custom; Opus-Style Gaming/Dynamic Gaming/Cinematic Gaming/AI Auto; YouTube/TikTok/Both. Defaults3,10s,Opus,Both. Source rights are recorded. No paid AI call is required.
- Campaign requirements retain source evidence. Mandatory wording/tags are enforced before optional text; uncertainties remain review tasks. Campaign/platform conflicts are shown and rechecked before publication.
- Distinct timestamp-grounded windows, batched bounded model evaluations, actual ending checks and actual-render observations. Known rating/title/menu/blank-only sampled windows are excluded from new gaming selection; insufficient evidence returns fewer clips rather than duplicate filler.
- Portrait1080×1920 H.264/AAC, default30FPS and optional30/60 in the editor. Wide gameplay stays undistorted over synchronized source-derived Gaussian blur with restrained darkening. Existing validated captions, effects, audio normalization and timing remain. No application watermark, end card, purchased sound or copied reference asset is added. Embedded third-party branding is preserved.
- Automatically populated platform text, three YouTube title suggestions and three TikTok alternatives; separate on-video headline. If copy generation fails after actual-render analysis, observation-based recovery retains review status. Missing visual evidence remains unavailable rather than invented copy.
- Searchable, collapsible campaign groups include legacy outputs. Cards provide Preview/Edit/Download/Publish, exact version/compliance state, platform publication jobs and actual linked-post KPIs. Queued/private/inbox states are distinct from confirmed public posts.
- One simple editor: headline, extra text, timing,30/60FPS, style, publication text/tags, subtitle corrections and saved-version restoration. Metadata-only changes reuse video; visual changes render only that clip as a new version. Selective field regeneration preserves unrelated manual copy and other platforms. Detailed review remains an optional modal, not another sidebar editor.
- One bounded automatic readability/framing repair can run after initial inspection when a supported correction exists. The result is inspected again; failures or a worse sampled check retain the original decoded output. It never loops for a high score and never overrides a manual-edit job.
- Seven-factor editorial rubric: hook20, gameplay20, editing15, headline15, visual/audio10, metadata10, audience10. Confidence is explicitly low; scores are not probabilities or predicted views. Visual/audio currently uses visual proxies and does not independently measure audio synchronization.

## Account connections, publishing and real analytics

Settings exposes configuration diagnostics, exact callbacks, granted scopes, reconnect and disconnect. Secrets and encrypted tokens stay on the backend. Invalid refresh grants mark reauthorization required. YouTube uses official OAuth/resumable uploads; TikTok uses approved Direct Post or inbox FILE_UPLOAD, as permitted by granted scopes. Version approval, compliance, exact final consent and idempotent per-platform jobs remain required.

TikTok inbox completion is `uploaded_draft`: finish publishing inside TikTok and copy the generated caption there. It never creates an inferred public URL or KPI. Direct Post retains creator-information/privacy/music/commercial-content checks and actual audit restrictions. A personal upload utility is not automatically eligible for public Direct Post approval. See [setup and official references](SOCIAL_SETUP.md).

Analytics separates lifetime snapshots from dated reports. It supplies available views/likes/comments/shares, engagement components, published platform posts/average observed views, identity-matched account subscriber/follower captures, range growth with a real baseline, history, dated charts, platform comparison and campaign/video/style/date filters. An idle worker attempts one authorized account sync per15-minute gate; the dashboard refreshes saved results every minute and supports manual sync/import. Missing permission, hidden statistics and unsupported fields stay null. First7/30-calendar-day views require complete daily coverage; rolling first24h views, retention curves and per-clip audience gains are unavailable in the current adapters. Watch minutes use available dated authorized reports. Learning requires sufficient distinct actual posts and reports descriptive patterns, never guaranteed outcomes or fake results.

No live account credentials or approved developer apps were available. Real OAuth, actual YouTube/TikTok upload and authenticated KPI synchronization were **not** performed. Controlled HTTP tests cover protocol, identity matching, publication association, null metrics, audience growth, inbox behavior, refresh/backoff and idempotence. Required external steps remain developer configuration, approved scopes/callbacks, account authorization, applicable review/audit, provider quotas and explicit user publication consent.

## Preservation and changed files

`frontend/components/unified-workspace.tsx`, `unified-create.tsx`, `generated-gallery.tsx`, `clip-editor.tsx` and the existing `factory.tsx`, `studio.tsx`, `social-studio.tsx`, `workspace-settings.tsx`, `app/page.tsx`, `app/globals.css` implement the consolidated UI. Existing browser storage/renderer and detailed editor remain.

`backend/app/studio.py` adds enriched legacy-inclusive gallery, bounded URL import and atomic versioned edit/restore/selective regeneration. `services/url_import.py`, `local_auto.py`, `local_highlights.py`, `studio_metadata.py`, `media.py`, `schemas.py`, `viral_score.py` extend the existing processing architecture. `performance.py`, `social.py`, `publishing.py`, `models.py`, `worker.py` extend observations and optional official integrations. Local requirements and the license inventory include optional yt-dlp; no user media/model weights are committed.

Migration `c730ea230002_account_observations.py` adds only timestamped account observations after the existing studio migration. Upgrade existing installations with `cd backend; ..\.venv\Scripts\python.exe -m alembic upgrade head` using their normal database environment. The migration test upgrades an old schema containing a saved user and verifies preservation plus new tables.

## Actual local acceptance

The explicitly identified reference videos in Downloads were decoded and compared; see [reference analysis](REDESIGN_REFERENCE_ANALYSIS.md). The supplied app example is a1.83s synthetic rendering fixture, so it cannot establish gaming-pacing parity with the45s Opus example.

Actual source: the existing151.67s4K Warzone trailer in the user-provided local folder. Original files were read and preserved. A first native batch created three10s portrait clips in306.39s, with first clip in149.89s, local model inference, actual-render inspection and automatically populated YouTube/TikTok metadata. The PDF acceptance imported and locally analyzed an owned test document containing mandatory `#Warzone #LocalReview` and `Local draft for review.`; three outputs appeared under Unified PDF campaign acceptance. All selected platform variants begin with those mandatory hashtags. Ambiguities correctly remain REVIEW_REQUIRED. No actual supplied footage was automatically approved or published.

All acceptance data are ignored local artifacts under:

`.runtime/studio-acceptance-77e58d330da9459fbec12c34cc0d229f/`

The PDF batch video files are under its `media/local-workspace/clips/` directory:

- `7bdf1904-1289-437d-aced-073a9339d157/v1.mp4`
- `55db6827-8f16-496d-b39e-c3f4ae93cd9f/v1.mp4`
- `7c57d28b-3490-4d3d-ad7a-80ac374b856b/v1.mp4`

A pause interrupted that batch after two saved outputs. Resuming the worker completed the third without overwriting the first two. Its wall-clock duration includes interruption and is not a fresh-run benchmark. Local result evidence: `.runtime/redesign-pdf-result.json`.

Actual browser editing on clip `e581e6db-a753-4f03-ae40-77c2929d785b`: metadata-only edit v1→v2 kept the exact video/plan and TikTok copy; headline edit rendered only that clip v2→v3 while keeping the manual description; restore of v2 created v4 with the original headline and manual description. Every other clip version stayed unchanged. Evidence: `.runtime/redesign-edit-verification.json`. Preview played to10.0/10.0s at1080×1920, readyState4, no media error. Controlled generated-media tests separately exercise review/approval/export; they do not establish rights or campaign eligibility for the Warzone trailer.

## Validation and limits

Final local checks: **223 backend tests passed** (five dependency/test-clock deprecation warnings), **56 browser workspace/API/creative checks passed**, TypeScript and native production build passed, and GitHub Pages static build passed. Static export emits the expected warning that server headers do not apply. No failing tests remain. Fresh migration and existing-record preservation are included. Native and Pages builds are separate; the public Pages site does not run the native model/backend. This branch is source delivery, not a claim that main/Pages has deployed it.

The local4B vision model can overinterpret footage, misdescribe actions or include unsuitable context. The initial run included a title-card opening, which motivated the new static-card exclusion; the filter cannot guarantee continuously strong gameplay or semantic truth. Sparse12-frame source analysis and three rendered samples do not establish complete narrative payoff, correct every word, or match a professional editor. Continuous person/player tracking and source separation remain unavailable. OCR still requires optional local Tesseract. The supplied input is an official trailer rather than a continuous creator gameplay recording. These limitations prevent claiming consistent Opus-level quality or publication-ready semantic accuracy without actual review.

The bounded polish path is tested with controlled assessments and real FFmpeg encoding, including original preservation on a failed second render. It is not a verified perceptual improvement across real gameplay. URL import is tested with destination guards and a controlled downloader, not an unprovided live authorized URL. Offline research is explicit when optional official public-data credentials/results are absent. There are no fake metrics, guaranteed virality, fabricated published links or paid provider fallback.

### Final filtered batch and metadata evidence

The final UI-started batch is project `1889fec2-7f20-46f3-bc33-f2b8ad27a20d`, job `f57a8391-0a31-47e3-aa46-3d0774a3c735`, completed with three actual10s outputs. Files in the same ignored media directory:

- `443c52a4-dbd6-489d-810a-00599ff50813/v1.mp4`, source9.693–19.693s.
- `e680b656-e827-472d-a330-f46615eac9df/v1.mp4`, source36.4864–46.4864s.
- `e7f7734c-7468-45a9-a102-bcaf6d977bcd/v1.mp4`, source23.39–33.39s.

Actual output inspection showed that a source sample describing an aircraft did not prevent a logo/title-card opening elsewhere in that10s range. The sampled-window filter therefore does **not** establish continuous gameplay quality. A further deterministic evidence filter excludes clear black-background text/logo/rating/menu samples from publication-copy inputs; all three packages were regenerated from their retained actual scene observations in23.73/20.55/19.14s. This changes metadata versions, not video files. The third recommended title now describes gloved hands above the cityscape rather than the logo. The small model still occasionally produces awkward, truncated or mixed-language copy, so these remain review-required drafts. The automation is implemented; consistent professional editorial acceptance remains unmet.

Evidence: `.runtime/redesign-filtered-result.json`, `.runtime/redesign-filtered-copy-check.json`. All three have3 YouTube title suggestions,3 TikTok alternatives, required campaign tags first, real render measurements and current-version review status. No public post, real KPI or semantic campaign approval is claimed.

Selective regeneration was also exercised through the real browser/local model: the train clip's YouTube title was regenerated to **Train interior with blue seat and open door**, creating v3 while preserving every other YouTube variant field, all TikTok copy, the plan and the exact video URL. Evidence: `.runtime/redesign-selective-verification.json`. Its browser Download action saved `C:\Users\duled\Downloads\ai-clip-443c52a4.mp4`; its SHA-256 matches the stored real MP4. Native Settings shows disabled/unconfigured accounts honestly, and Analytics shows unavailable metrics rather than fabricated zero engagement. The built static browser edition was separately opened locally and its five navigation sections/manual flow verified. Screenshot: `.runtime/redesign-gallery-verified.jpg`.
