# Local Ultimate implementation record

Branch: `codex/local-ultimate`. GitHub Pages remains the browser/manual edition. Local AI uses the existing native FastAPI backend, database, durable worker and FFmpeg renderer. All inference must use a loopback Ollama server; `FREE_MODE=true` continues blocking hosted AI and external storage/publishing.

## Phase 1 — Ollama provider

Configuration lives in `.env.example`: model `qwen3-vl:4b`, endpoint `http://127.0.0.1:11434`, context4096, one inference at a time, bounded timeout/retries/output. `/api/local-ai/status` reports actual model readiness. Structured responses use JSON schemas and Pydantic validation. No missing-model substitution or fabricated results is permitted. Models are unloaded after inference to make room for later processing.

Unit contract tests are separate from actual inference and GPU validation; later evidence is recorded here as it becomes available. Downloading a model is not an inference acceptance test.

Official API references: [structured outputs](https://docs.ollama.com/capabilities/structured-outputs), [vision](https://docs.ollama.com/capabilities/vision), [chat](https://docs.ollama.com/api/chat).

Phase1 validation: 24 provider tests passed. A real `qwen3-vl:4b` request described a sampled frame from the supplied video and returned schema-valid source content and uncertainty in69.19seconds. NVIDIA memory was445MiB before/peak, and Ollama reported `size_vram:0`; this proves local CPU inference, not GPU acceleration. Raw evidence stays ignored in `.runtime/phase1-real.json`.
