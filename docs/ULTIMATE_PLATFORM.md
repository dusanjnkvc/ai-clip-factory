# Ultimate platform implementation

Branch: `codex/ultimate-platform`, based on the working `codex/local-ultimate` release. This upgrade preserves Next.js/React, FastAPI/SQLAlchemy, the existing database, local Ollama, worker, native FFmpeg and browser edition. New capabilities belong to the localhost edition; GitHub Pages cannot run the native worker or secure OAuth callbacks.

## Implementation record

1. Repository and license audit: inspected native/browser import, campaigns, renderer, jobs, versions, compliance, YouTube OAuth/upload, CSV analytics, dependencies and docs. Audited exact Chopify/AutoShorts source commits and licenses; use equivalent implementations instead of importing either app. See `THIRD_PARTY_LICENSES.md`.
2. Campaign engine, then a working import-to-three-drafts-to-review slice are the first implementation targets. Subsequent slices add actual-render scoring, manual version approval, official social adapters, actual analytics/learning and optimization. Record verified results below; incomplete sections must not be presented as completed.

Baseline release checks: 176 backend tests, 59 frontend checks and native/static builds passed before this upgrade. The prior release's real local acceptance and GPU measurements are in `LOCAL_ULTIMATE.md`; they do not establish performance or correctness of this new three-draft workflow.

Campaign slice: local PDF page extraction, safe UTF-8 TXT/DOCX imports and bounded optional Tesseract/Poppler OCR retain source sections. Exact title/description/on-video requirements, prohibited platforms, branding/logo/resolution and other mandatory terms survive schema validation. Contradictions remain explicit. Required hashtags retain exact spelling/order before optional tags across native generated and manual metadata; compliance rejects reordered tags and missing exact wording. OCR requires separately installed executables and is not claimed tested on a real scan yet. Semantic branding/on-video checks require actual human evidence.
