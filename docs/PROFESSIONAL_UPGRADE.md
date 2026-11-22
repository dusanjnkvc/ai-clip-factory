# Professional upgrade: repository audit and implementation ledger

Audit date: November 21, 2026. Baseline commit `bcfb9e24d6c2db6fb0642c0855b1170d9d9a74a5`. Restore tag `restore/pre-professional-editor-20261121`; verified SQLite backups in ignored `.runtime/professional-restore-20261121/`. Baseline: 225 backend and 63 browser/API/creative/WASM checks passed.

## Existing functionality to preserve

The native workspace already has five tabs, Ollama Qwen3-VL 4B vision/text inference, Faster-Whisper CPU int8 with word timestamps, source-wide scene/audio measurements, bounded frame interpretation, distinct candidate ranking, source-grounded metadata, actual-render editorial review, cached transcripts/analysis, per-clip versioning, official optional social integrations and real authorized performance observations. FFmpeg supports source-derived blur, numeric crop motion, restrained effects, rate changes, freeze accents and audio normalization. Remotion 4.0.545 renders a real shared composition in browser or native Node/Chromium. Browser-only sources/rules/versions use IndexedDB; 1,500 MB inputs use WORKERFS.

Chopify and AutoShorts were studied, not installed as external clipping servers. Native modules implement equivalent validated source analysis and edit decisions; no proprietary source or protected commercial assets are used. The installed Remotion integration is real, but the current modal editor exposes only a subset of it.

## Gaps and risks

- Native and static creation shells differ. Browser-only editorial templates are not local AI. Advanced inference requires the existing loopback backend; GitHub Pages cannot itself run CUDA/NVENC or hold OAuth secrets.
- Editing is spread across modals/detailed forms; Edit does not route back into Create Clips. There is no consistent interactive asset-layer timeline, durable editable draft, reusable branding library or template application.
- Generic local vision descriptions are not validated kill/victory/facial-emotion detectors. Speech-free motion is measured, but game-specific event accuracy has not been established.
- The seven-factor editorial rubric differs from the requested six-factor weights. Scores are low-confidence judgments, not calibrated view forecasts.
- Static legacy financial views remain reachable in source; remove financial UI while retaining old stored records.
- Social apps/approved scopes and user authorization remain external prerequisites. No invented connections, publishing, analytics or trend data.

## Technology verification

| Project | Pinned inspected head | License reported by GitHub | Maintenance evidence | Decision |
|---|---|---|---|---|
| [mehbul/chopify](https://github.com/mehbul/chopify) | `9363aa42b447` | MIT | Not archived; pushed 2026-11-21T13:02:03Z | Reuse the existing bounded local integration; no wholesale application install. |
| [mutonby/openshorts](https://github.com/mutonby/openshorts) | `e3e8a666e6ae` | MIT | Not archived; pushed 2026-11-21T14:51:28Z | Core MIT; cloud/ has separate commercial terms. Inspect picker/tracking architecture only; do not import billing, paid defaults or an independent app. |
| [Anil-matcha/AI-Youtube-Shorts-Generator](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator) | `8c9ac3103a13` | MIT | Not archived; pushed 2026-11-21T12:34:29Z | Inspect transcript picker/crop workflow; existing multimodal pipeline supplies most functions. Do not adopt mandatory cloud credentials. |
| [remotion-dev/remotion](https://github.com/remotion-dev/remotion) | `970849fc1921` | NOASSERTION | Not archived; pushed 2026-11-20T21:05:57Z | Keep aligned 4.0.545. Custom Free License for eligible personal/small entities; not MIT. |
| [konvajs/konva](https://github.com/konvajs/konva) | `bf1927c1cfec` | NOASSERTION | Not archived; pushed 2026-11-20T02:23:32Z | MIT verified in official README; DOM pointer controls over the existing Remotion Player provide equivalent editor manipulation without a second canvas renderer. |
| [FFmpeg/FFmpeg](https://github.com/FFmpeg/FFmpeg) | `47f7313e6a33` | NOASSERTION | Not archived; pushed 2026-11-21T19:20:35Z | Keep current separate process/WASM. Build-dependent LGPL/GPL; existing source distribution obligations remain. |
| [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) | `6cb639e70786` | MIT | Not archived; pushed 2026-11-12T09:05:56Z | Reuse the existing bounded local integration; no wholesale application install. |
| [google-ai-edge/mediapipe](https://github.com/google-ai-edge/mediapipe) | `3ad0cf160665` | Apache-2.0 | Not archived; pushed 2026-11-21T08:38:39Z | Apache-2.0 framework; model licenses separate. Optional detector only after actual accuracy/hardware validation; not a universal game-event model. |
| [Breakthrough/PySceneDetect](https://github.com/Breakthrough/PySceneDetect) | `e51a306ce0d9` | BSD-3-Clause | Not archived; pushed 2026-11-21T01:52:30Z | Reuse the existing bounded local integration; no wholesale application install. |
| [opencv/opencv](https://github.com/opencv/opencv) | `13778986a86c` | Apache-2.0 | Not archived; pushed 2026-11-21T15:37:11Z | Reuse the existing bounded local integration; no wholesale application install. |
| [ollama/ollama](https://github.com/ollama/ollama) | `2bd4d6aabdf4` | MIT | Not archived; pushed 2026-11-21T18:58:38Z | Reuse the existing bounded local integration; no wholesale application install. |
| [shubhxtech/AutoShorts](https://github.com/shubhxtech/AutoShorts) | `72d7f4e8bfb7` | MIT | Not archived; pushed 2026-10-25T10:58:28Z | Reuse the existing bounded local integration; no wholesale application install. |

Availability and maintenance metadata were fetched from the official GitHub repositories at the pinned heads above. A recent push is maintenance evidence, not a security guarantee. The existing lockfiles and package audit cover installed dependencies; unused upstream dependencies are not installed or certified.

## Shared architecture

Keep the original five navigation items and dark/purple identity. Integrate automatic generation and an optional advanced editor into Create Clips. Store a versioned editor state on the existing validated plan, with owned asset references, timed layers and caption appearance; keep source cuts/AI evidence/metadata on that same plan and clip record. Browser and native renderers resolve owned assets into the same Remotion composition. Draft autosave must not enqueue AI or rendering. Existing immutable clip versions and explicit export/publishing review remain.

The RTX 4070 Laptop 8 GB VRAM setup retains one 4B quantized vision model at a time, bounded frame batches, CPU int8 speech inference and capability-tested NVENC. Larger model quality is not assumed to fit available VRAM. No model download or paid service is silently required.

## Implemented upgrade

- Create Clips opens in Automatic AI Mode. Advanced Manual Mode and campaign review stay inside that tab, with the original five navigation items and dark/purple styling.
- Automatic projects produce the same editable plan used by the manual editor. Optional reference profiles, transparent logos, usernames and saved designs apply across generated clips. Required campaign wording remains above custom layers; required tags and mentions lead saved publication text.
- The editor offers timed text/image/video/audio layers, canvas manipulation, timeline movement/trimming, source splits, speed/freezes, crop/layout controls, video transforms/color adjustments, layer ordering/visibility/locking, undo/redo, revision-checked autosave, saved render history and reusable designs. Small appearance changes preview in Remotion; timing/framing changes rebuild a clean video proxy without AI.
- Ten caption presets have font, weight, colors, outline, shadow, background, position, rotation, opacity, spacing, alignment, case and animation controls. Karaoke uses actual supplied word times. Uploaded phrase cues retain phrase timing; word times are not fabricated.
- Owned assets are reused in both renderers. Images become canonical PNG; simple SVG geometry is checked and rasterized in the browser, and native audio becomes bounded canonical WAV. Assets used by saved clips/versions/drafts/designs cannot be archived. Project duplication copies media into an independent version and clears approval.
- Native Settings displays actual local model/capability availability, optional GPU readings, disk space, and saved processing/resolution/frame-rate defaults. Missing GPU readings remain unavailable.
- A bounded source-wide motion survey supplements scene/audio measurements. Persistent corner-face detections can propose an adjustable facecam/gameplay layout. Original-source crop rectangles drive both native and browser preparation. These proposals do not establish streamer identity or game events.
- Source-hashed measurements, speech and model observations are cached separately. A survey-version upgrade retains valid observations from the same source/model/transcript/context/budget. New footage/budgets still receive bounded deeper inspection. Manual clip changes do not run source analysis again.
- Estimated scores now default to hook25 / entertainment20 / retention20 / editing15 / metadata10 / audience10. The explanation identifies offline heuristic inputs and their limits. Existing saved scores and explicit legacy weight configuration remain intact.
- URL validation supports canonical public YouTube videos, Twitch recordings/clips and Kick recording URLs. Live channels, credentials, playlists and arbitrary download hosts are rejected. External restrictions still require an authorized local file.
- Native gallery review/approval remains available alongside Edit Clip; metadata is editable in the shared editor. Metadata-only saves reuse the existing video. Browser analytics shows actual recorded observations; finance views are removed, while historical records remain stored.

## Acceptance evidence

The baseline passed 225 backend and 63 browser checks. During this upgrade the complete regression run passed 241 backend and 67 browser/API/creative/real-WASM checks before later review/duplication additions. The final complete run passed **244 backend checks and 69 browser/API/creative/real-WASM checks**. Native and Pages production builds pass; the production npm audit reports zero known vulnerabilities. Later UI-only grouping/link changes also receive the normal build and browser acceptance checks.

Actual browser acceptance imported a transparent PNG, added animated text, resized/repositioned/rotated the logo, changed opacity, exercised undo/redo, saved a reusable design and rendered a new version. The downloaded 1080x1920 H.264/AAC MP4 passed complete decode, and an extracted frame confirmed custom text, transparent logo and mandatory campaign wording. The autosaved caption style and split timeline survived reopening; Edit Clip routed into Create Clips. Local evidence is in ignored `.runtime/professional-acceptance/`.

An independent native Remotion export of owned generated test footage included a transparent logo, timed text, actual known test-caption times, mandatory wording, and an owned generated audio layer. It produced a fully decoded 1080x1920 H.264/AAC MP4. These fixtures establish rendering behavior, not gameplay or ASR accuracy. Real WASM tests also decode rate/freezes and facecam-layout output.

The authorized source folder contains two silent store/reward screen recordings and a 151.67-second Warzone trailer. Sampled contact sheets show gameplay/cinematic character faces, with no streamer facecam in the inspected samples. A new survey measured 152 periodic activity samples; no recording-specific timestamps or detector rules were introduced. Positive streamer-facecam, kills, victories, funny reactions, word accuracy and long Twitch performance cannot be established from this set. The user explicitly allowed continuing other implementation when suitable footage is absent.

A fresh three-clip branded automatic test uses the authorized trailer and the existing local model. Its initial redundant-inference run was cancelled through the app after exposing cache-upgrade inefficiency; the corrected retry reuses valid source observations and retains the original footage. Final outcome is recorded after it reaches a terminal state. GPU memory measurement was unavailable because Windows denied `nvidia-smi`; a zero measurement is not claimed.

## Practical limits and remaining acceptance

- This is an integrated local editor upgrade, not a claim of complete CapCut/OpusClip/Eklipse parity. No validated universal kill/victory/emotion or identity-aware speaker tracker is shipped. The motion/vision evidence proposes candidates that require review; users can adjust selections and facecam crops.
- Native inference/transcription and OAuth secrets need the local service. GitHub Pages supplies free browser editing and measured editorial suggestions; it cannot run the local CUDA service. Browser storage remains separate from native disk storage.
- Caption translation, isolated speech-stem separation, arbitrary font uploads, automatic background-image replacement and universal face/UI avoidance are not implemented as completed features. Correct/translate cue text manually, use owned audio tracks, packaged fonts and manual placement. Silence edits remain source-bound scene decisions rather than a promise to understand every pause.
- No registered owner Google/TikTok apps or authorized test accounts were supplied. Existing official authorization/publishing/analytics adapters and setup guidance are retained, but live connection, posting, trend research and metric synchronization cannot be claimed tested here. Manual upload packages and recorded actual post URLs remain available.
- Actual external URL downloading and multi-hour Twitch performance remain unverified; no authorized URL or long streamer recording was supplied. The source-folder recordings establish local file handling and rendering only.
- New dependencies: Pillow13.0.0 and the OpenCV4.14.0.94 pin in local-AI requirements. OpenCV5 moved Haar detection to contrib; the pinned4.x package retains the bundled detector. Motion surveying still works without that detector and reports its absence. See THIRD_PARTY_LICENSES.md and the installed-license inventory.

## Phase ledger

1. Audit/restore: verified, with immutable tag and checked SQLite backups.
2. Multimodal analysis: existing ASR/vision/audio/scene pipeline retained, source-wide survey and cache migration added; game-event and positive facecam accuracy still require suitable footage.
3–5. Shared editor/captions/assets/designs/campaign review: implemented with real browser/native export acceptance and contract checks.
6. Metadata/scoring: automatic source-grounded proposals retained, required campaign text prioritized, six-factor default implemented; no guaranteed reach or invented live trends.
7. Gallery: integrated Edit Clip, version review/approval and independent duplication. The browser gallery adds campaign groups, search, status filters, sorting and duplication. Bulk export remains limited to existing approved campaign/project package workflows.
8. Publishing/analytics: official adapters retained; real account acceptance depends on owner developer apps and authorized accounts. Financial UI removed.
9. Regression/build/deployment: final verification in progress; exact final results appended below.
