# Local Ultimate implementation record

Branch: `codex/local-ultimate`. GitHub Pages remains the browser/manual edition. Local AI uses the existing native FastAPI backend, database, durable worker and FFmpeg renderer. All inference must use a loopback Ollama server; `FREE_MODE=true` continues blocking hosted AI and external storage/publishing.

## Phase 1 — Ollama provider

Configuration lives in `.env.example`: model `qwen3-vl:4b`, endpoint `http://127.0.0.1:11434`, context4096, one inference at a time, bounded timeout/retries/output. `/api/local-ai/status` reports actual model readiness. Structured responses use JSON schemas and Pydantic validation. No missing-model substitution or fabricated results is permitted. Models are unloaded after inference to make room for later processing.

Unit contract tests are separate from actual inference and GPU validation; later evidence is recorded here as it becomes available. Downloading a model is not an inference acceptance test.

Official API references: [structured outputs](https://docs.ollama.com/capabilities/structured-outputs), [vision](https://docs.ollama.com/capabilities/vision), [chat](https://docs.ollama.com/api/chat).

Phase1 validation: 24 provider tests passed. A real `qwen3-vl:4b` request described a sampled frame from the supplied video and returned schema-valid source content and uncertainty in69.19seconds. NVIDIA memory was445MiB before/peak, and Ollama reported `size_vram:0`; this proves local CPU inference, not GPU acceleration. Raw evidence stays ignored in `.runtime/phase1-real.json`.

Additional real GPU test: an isolated loopback Ollama process on11435 with Vulkan disabled detected CUDA on the RTX4070. The same real vision request completed in24.09seconds; measured NVIDIA memory peaked4912MiB of8188MiB (baseline445MiB). Evidence: ignored `.runtime/phase1-real-gpu.json`. Existing Ollama11434 was not changed. All104 existing/provider backend tests passed after phase1. This one request is not a whole-pipeline memory benchmark.

## Phase 2 — Real source analysis

Added `local_analysis.py`, `test_local_analysis.py` and optional `requirements-local-ai.txt` (SceneDetect headless0.7.3, Faster-whisper1.2.1). Install with the existing virtual environment and `pip install -r backend/requirements-local-ai.txt`.

The analyzer probes/hash-checks actual files, detects visual scene cuts with PySceneDetect, decodes bounded OpenCV frames, measures source audio RMS, uses CPU int8 Faster-whisper for real word/phrase timing, and asks the local vision model for timestamp-linked observations with explicit uncertainty. It preserves uploaded cues and invents neither dialogue nor word alignment. Sparse-frame interpretations are not independently verified events. The model, cache settings and source SHA participate in a validated atomic cache identity. Speech recognition and vision run sequentially with model-release barriers.

All15 analyzer tests passed, including actual scene cut/pixel/audio measurements. Semantic test doubles are not evidence of local AI interpretation. A cold PyAV native import took substantially longer than subsequent imports on this Windows installation. Real source/GPU validation is recorded separately when complete.

Faster-whisper refuses uncached weights by default. Explicit first-run setup can set `LOCAL_AI_ALLOW_MODEL_DOWNLOAD=true` to download its free model; downloading is not hosted inference. CPU int8 avoids requiring CUDA/cuDNN in the speech recognizer.

References: [SceneDetect](https://www.scenedetect.com/docs/latest/api.html), [Faster-whisper](https://github.com/SYSTRAN/faster-whisper), [CTranslate2 model unloading](https://opennmt.net/CTranslate2/python/ctranslate2.models.Whisper.html).

Real model validation caught an overlong two-frame response. The analyzer now uses exact timestamp/count-constrained schemas and short fields, defaults to one frame, and splits token-limited larger batches without expanding the context or memory limit. Single-frame failure remains an explicit error. This behavior has regression coverage.

Real phase2 validation: `qwen3-vl:4b-instruct` analyzed the supplied121.29-second First Free Pack video in46.31seconds:18 measured scene cuts,4 real frames/findings, and zero invented words for the silent source. The findings distinguish website, card reveal, loading screen and product page. These are still uncertain model interpretations requiring final review. Additional supplied-video and speech tests continue separately.

The requested default remains `qwen3-vl:4b`. Current public4b weights resolve to the thinking variant; real bounded batches exhausted the token budget even with `think:false`. For the tested local configuration explicitly set `OLLAMA_MODEL=qwen3-vl:4b-instruct`. This is the4B instruct variant, not a hosted fallback. [Official tags](https://ollama.com/library/qwen3-vl/tags) and [thinking controls](https://docs.ollama.com/capabilities/thinking).

Additional phase2 evidence: the31.6-second PS5 product video completed in47.47seconds with7 scene cuts and4 distinct source findings. The two-source run peaked4923MiB GPU memory, baseline450MiB. The4K trailer yielded145 measured cuts, then exposed a Faster-whisper/PyAV audio-decoding incompatibility; no transcript or full trailer analysis was reported as successful. A safe FFmpeg PCM decoder fix is being validated separately.

## Phase 3 — Source-grounded highlight ranking

Added `local_highlights.py` and28 tests. Eight configurable normalized factors combine actual frames, uncertain model findings, source continuity, audio evidence, audience and campaign rules. Loudness alone cannot select a highlight. Contiguous chronological windows preserve source integrity; overlapping near-duplicates are suppressed and insufficient footage produces fewer candidates with a reason. Scores are explained heuristics, not performance predictions or semantic approval.

The saved real first-video analysis produced three distinct20-second windows:27.9303–47.9303,62.3323–82.3323,88.5575–108.5575. Ranking itself makes no new inference request. Native campaign schemas/parser/metadata/compliance now retain automation, original-footage, music/voice/promotion restrictions and required HTTPS links. Explicit automation prohibitions stop automatic candidate selection. Semantic requirements still need review.

All150 backend tests passed after the phase3 changes, including28 ranking and3 new native-rule regression tests. This does not establish successful automatic editing or metadata generation; those phases follow.

### Audio decoder compatibility correction

A real trailer test exposed `av.open(metadata_errors=...)` incompatibility in the installed Faster-whisper/PyAV combination. Speech input now uses the existing safe FFmpeg demuxer/container whitelist to decode actual16kHz mono float32 audio, with duration/memory/timeout/cancellation bounds, before passing the waveform to Faster-whisper. No renderer or database was replaced. All17 analyzer tests pass, including actual audio decoding. The real151.67-second trailer's local CPUint8 recognizer ran in4.94seconds and returned one word; this proves inference, not transcript accuracy. Sparse speech/music still needs review. Evidence remains ignored in `.runtime/warzone-transcript.json`.

## Phase 4 — Automatic timeline assembly

Added `local_timeline.py` and14 tests. Source-bound ranked windows become High-Energy Gaming, Cinematic Storytelling, or Suspense and Payoff plans with chronological cuts, restrained numeric crop motion/zoom, source-supported hook text and original-or-muted audio. Native Scene/ClipPlan contracts now validate crop endpoints, whitelisted transitions/effects, local-AI provenance and audio treatment. Semantic local-AI context remains REVIEW_REQUIRED.

A bounded model evaluation may only score validated candidate IDs; it cannot create a timestamp, introduce source material or select an unavailable plan. Its highest score selects one winner (local ranking breaks ties), with all alternatives kept internally. Missing/invalid model evaluation stops rather than creating a fallback winner.

All166 backend tests passed, including14 timeline tests. The actual saved first-video findings assemble three20-second styles with2,2 and4 purposeful shots. Unit evaluation uses a controlled provider; real winner selection is pending the coordinated end-to-end run. Applying the new render parameters is the next phase; assembly alone is not a rendered-edit acceptance test.

## Phase 5 — Native rendering enhancements (November18)

The existing FFmpeg renderer now applies validated numeric crop motion, short shot fades, contrast/retro treatment and actual mute. It retains source-timed ASS captions and visible opening hook text, output probing and complete decoding. No rendering backend was replaced. Silent audio bypasses loudness normalization because the packaged FFmpeg7.1 produced NaN samples when normalizing silence. All28 relevant renderer/pipeline tests pass, including a real1080×1920 animated encode/decode and measured silent audio. Full user-video autonomous rendering remains an end-to-end acceptance task.

## Phase 6 — Optional public trend research

Added `trends.py` and two passing contract tests. It uses only the official YouTube search/videos API, bounded recent public results, canonical URLs/dates, actual available metrics, and a daily SQLite cache/request-reservation ledger. API keys remain in environment variables and are not copied into results. A single snapshot is only a research-supported suggestion, never a verified growth/viral claim or proof of TikTok/Reels trends. Missing credentials, quota/errors or cache failures return explicit unavailable status so local metadata can continue. No live API research was claimed: tests use controlled HTTP responses and no research key is configured for acceptance yet.

## Phase 7 — Metadata selection

Added `local_metadata.py` and two passing tests. A structured local-model request creates three internally retained alternatives using only winning-edit frame evidence and selected transcript. Unknown evidence IDs stop selection. Required campaign text/links/tags survive formatting and platform validation. One editorially scored package is recommended; the source hook remains the visible opening. No retention/view guarantees are made. Missing research is explicitly classified as generally relevant local content. Tests use a controlled provider; real model metadata is pending end-to-end acceptance.

## Phase 8 — AUTO CREATE integration

Added a native Auto Create screen, loopback-only job/result/cancel/package endpoints, local orchestration service, and `scripts/local-ai.ps1`. Existing sources, rights checks, SQL queue, candidate/plan/clip/version storage and manual clipping remain available. Automatic jobs render only the selected winner, reserve zero paid budget, and serialize local model phases before rendering. The final screen exposes one recommended title/description/hashtag package, video and package downloads. Cancellation interrupts model/analysis stages; an active native encode stops exposing its result after cancellation rather than promising instantaneous subprocess cancellation.

Two API/worker tests pass using controlled inference plus real FFmpeg output, confirming one export, persistence, zero budget, cancellation, automation prohibition and preserved manual endpoint. The existing171-test suite and native production build passed before these additions; final combined checks and real full-inference/UI acceptance follow.

### Windows startup

With Python3.12, Node and Ollama installed, create `.venv` and `.env` from `.env.example` if needed. First setup: `powershell -ExecutionPolicy Bypass -File scripts/local-ai.ps1 -Setup`. Later: `powershell -ExecutionPolicy Bypass -File scripts/local-ai.ps1`. The launcher uses the explicitly tested4B instruct variant and an isolated loopback11435 server with Vulkan disabled; the provider's requested4b default remains configurable. Downloads are free model/package downloads, not hosted inference. It does not alter the user's11434 server. Open http://localhost:3000 and select AUTO CREATE. Native uploads allow1500MB in this launcher for the supplied4K source; keep enough RAM/disk for upload buffering. GitHub Pages remains browser-only manual/assisted editing.
