# Implementation and verification status

The user selected a free manual workflow, then requested no login and hosting in a new GitHub repository. The default hosted topology is now a static browser edition; the native Python edition remains optional. Code, unit tests, real rendering, source publication, and live hosting are separate outcomes.

## Selected free browser edition

- No login, API key, application subscription, or billable media backend.
- Static Next.js export for GitHub Pages with FFmpeg WebAssembly assets.
- Videos and project records stored in IndexedDB on the current browser/device, rather than uploaded to GitHub.
- Manual clip range/crop and metadata, optional source-timed SRT/VTT, real rendering/preview/download, review-required campaign/compliance evidence, and manual publishing/submission workflows where implemented.
- Browser Creative Director with actual sampled-frame measurements, optional bounded audio RMS, editable source-bound concepts, eight render-safe styles, local drafts, campaign preflight, and source/editor-grounded publishing suggestions. This is an assisted manual feature; no semantic AI provider is enabled.
- Public application source in the dedicated Pages repository; `.env`, credentials, local databases, and user media remain excluded from Git.

The dedicated [repository](https://github.com/dusanjnkvc/ai-clip-factory) and [initial live Pages deployment](https://dusanjnkvc.github.io/ai-clip-factory/) were verified. A new configured build or push is not proof that a later change has deployed; each update needs its own successful Pages run. Browser renders require an open tab and available memory/CPU. Closing/reloading may interrupt jobs; clearing/evicting storage or changing profile/device can remove or hide records. There is no cloud backup, sync, or account recovery. Preserve originals and download important results.

This mode does not perform AI transcription, best-moment detection, semantic video understanding, or viral prediction. SRT/VTT cue times are supplied by the user; word times are not invented. The workflow uses manual review. It avoids paid service/API requirements but still uses the existing device, electricity, disk, and internet.

## Creative Director scope

The new Director feature is implemented for the browser edition. It offers High Engagement, Cinematic, and Creative Storytelling proposals when the real source supports distinct alternatives. Short footage can return fewer concepts with an explanation. Sampled visual changes, source-timed cues, and editing rules inform the proposals; no events, people, objects, reactions, or narrative outcome are recognized.

The interface supports source previews, shot order/times, manual reframing and crop motion, composition, text, captions, metadata, locks, undo/redo, and saved drafts. Split composition needs actual separate footage. Campaign-required original creator footage must be declared and used, and remains subject to human evidence review. Prohibited automation requires actual manual decisions and a recorded note; the note never establishes that the campaign allows the assisted workflow.

The browser renderer accepts real source shots, bounded animated crop, fit with source-derived blur, two-source split composition, cuts/short shot fades, contrast/retro treatment, source audio or mute, safe cue captions, and 1080 × 1920 / 720 × 1280 / 540 × 960 output. Fast/Premium are local encoding settings with no paid tier. Output is probed and fully decoded before completion. Fades are shot fades, not overlapping crossfades; captions have cue-level animation, not fabricated word alignment.

Local hook scores and diversity checks are explained heuristics. Publishing options use supplied source/editor text and required campaign metadata, not trend knowledge or AI optimization. Semantic checks remain REVIEW_REQUIRED; Director results retain `publish_ready: false`. Automatic subject tracking, semantic model analysis, generated voice/music, and invented missing footage are unavailable. See the [usage guide](CREATIVE_DIRECTOR.md).

## Optional free native edition

- `FREE_MODE=true` defaults to local manual processing and blocks hosted AI, S3, and direct social publishing even if old credentials exist.
- The nonproduction local workspace opens without login. It is a loopback convenience, not permission to expose an unauthenticated backend publicly.
- FastAPI, local SQLite/files, SQLAlchemy migrations, and a separate durable Python worker provide native FFmpeg rendering and persistent state.
- Optional local Docker/Compose uses PostgreSQL and shared media volumes. Docker is not required for the browser edition.
- Recorded post URLs/timestamps, submission countdowns, views CSV, and evidence-backed financial records remain distinct from actual publication, payment eligibility, and confirmed submission.

## Verification record

### Creative Director release checks — November 17, 2026

- 80 native backend tests passed, including existing real media rendering.
- 59 frontend checks passed: 18 browser rules, 8 local API lifecycle/persistence/preflight tests, 30 Creative Director/analyzer checks, and 3 real FFmpeg WASM checks. The WASM checks encode and fully decode actual vertical MP4s with crop motion, cue captions, paired footage, fit composition, fades, and treatments. API tests isolate storage/media; they do not claim browser IndexedDB or browser-worker coverage.
- Static Pages production build and TypeScript passed. Next.js warns that custom response headers do not apply to static exports; GitHub Pages owns HTTP headers.
- The local exported page returned HTTP 200. Interactive testing of the new Director interface could not be completed: Computer Use stopped because it could not confidently determine the browser URL. No later interactive success or screenshot is claimed.
- Initial deployment and CI at commit `24eed0a` both completed successfully. The Director release's own deployment result is recorded in the delivery after its workflow completes.


Free browser/native validation on November 16, 2026, before the Director update:

- 80 backend tests pass, including a real native free-mode render with supplied cue captions, a zero-spending allowance, disabled external services, and no-login workspace checks.
- 15 browser-rule boundary tests pass. TypeScript and the static GitHub Pages build pass.
- The exact static build was opened without login. A generated, rights-safe source was stored in IndexedDB, rendered by the browser's real FFmpeg WebAssembly engine with pasted SRT cue captions, and downloaded.
- The downloaded MP4 was independently inspected and fully decoded using native FFmpeg: 1080 × 1920, H.264, audio present, 1.83 seconds, 440,143 bytes. This is a short fixture, not a real-campaign performance benchmark or campaign approval.
- Browser persistence survived page reloads, and failed attempts remained visible while their source was preserved. The successful result correctly retains REVIEW_REQUIRED for unresolved campaign semantics.
- The dedicated public GitHub repository was created and Pages was configured to use Actions. Its Pages run completed successfully, and the live app was opened without login.

The Director update adds `frontend/scripts/test-creative.mjs` for source-bounded concept generation, style/safe-zone validation, diversity/manual edits, campaign restrictions, publishing provenance, and pure frame metrics. `frontend/scripts/test-wasm.mjs` exercises the real packaged WASM core through the production renderer, including animated crop/cue captions and paired footage/fit/fades/treatments. It uses a Node worker-shaped host; it is actual encoding/decoding coverage, not browser UI verification. The integrated update's final test/build/browser/deployment results must be recorded after those checks run, separately from the already verified initial deployment.

The earlier hosted-adapter MVP was validated on November 15, 2026 with 46 backend tests, a passing production build/TypeScript check, SQLite migrations, and browser checks including actual source upload/queueing and the honest missing-key state. Those historical checks do not verify later free/no-login/browser changes. Current results belong in the final delivery after the corresponding checks actually complete.

The native benchmark helper was checked for Python compilation/CLI help, guarded against starting a hosted job without explicit permission, and verified to construct a manual local payload in test-only fake-client checks. Those checks are not a live render benchmark. Docker was unavailable during the original run; containers, PostgreSQL, HTTPS provisioning, and cloud operation remain unverified unless later actual results say otherwise.

The final browser checks must distinguish a static build from actual FFmpeg WebAssembly output, IndexedDB persistence, no-login behavior, and the verified Pages deployment. Native FFmpeg tests cannot stand in for browser-engine tests, and native timing cannot be reported as browser timing.

## Boundaries and remaining work

- Local campaign parsing only recognizes explicit text patterns and retains source evidence. Unknown/contradictory rules need review. URLs are references; private pages are not scraped. Scanned documents/screenshots need manual rule entry in free mode where OCR is unavailable.
- A default/manual range is not a detected highlight. Context, source rights, framing, audio restrictions, branding, disclosures, and draft approval still need evidence-backed review.
- Without supplied timed captions, no transcription occurs. Caption-cue synchronization does not establish word-level speech alignment.
- Financial entries and views use explicit records/imports. Reported views do not establish payment eligibility. The app does not invent earnings, payouts, provider charges, or live analytics.
- Permanent source/version deletion is not automated. Native temporary files are cleaned by context managers; browser storage may be cleared independently by the browser/user.
- Continuous tracking, automatic gameplay event detection, learned optimization, live platform analytics, screenshot earnings extraction, automatic shared-pool/retainer settlement, and automatic Content Rewards submission are not implemented.
- Browser queues require the tab to stay open. Native lease/recovery behavior, database sharing, and multi-host scaling are separate concerns requiring validation before production use.
- A public native SaaS deployment would require appropriate authentication, account recovery, email verification, tenant administration, distributed rate limiting, security review, and infrastructure costs. It is outside the chosen free Pages path.

## Optional external native adapters

Hosted AI, cloud vision, official YouTube resumable publishing, and S3 remain disabled by default. Explicitly enabling `FREE_MODE=false` requires credentials, positive spending limits, eligibility, and authorization and can incur charges. No live provider request, social upload, campaign approval, monetary result, or deployment is inferred from unit tests.

## Performance

The original 5/10/15-minute goals for one/three/five AI-produced compliant clips were not established with representative media/credentials. The native free benchmark measures one manual range through the real API/worker. The browser edition must be measured in the actual target browser/device with its tab open. REVIEW_REQUIRED results must not be reported as publish-ready performance successes.
