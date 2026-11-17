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
