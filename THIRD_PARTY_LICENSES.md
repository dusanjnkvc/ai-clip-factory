# Third-party audit — November 18, 2026

This record covers the local Ultimate upgrade. Source code, separately installed executables, model weights and user footage have different terms. No reference-project assets or weights are bundled with this app.

## Reference repositories inspected

| Repository and pinned commit | Actual license | Decision |
|---|---|---|
| [Chopify](https://github.com/mehbul/chopify/tree/d576927bf3b764733c97ac1ad324aa9957b0885d) | MIT, Copyright 2026 Mehbul Islam | Studied `visual.py`, `score_clips.py`, caption/render and project modules. Equivalent implementations use existing bounded scene/frame/audio analysis, source-bound deduplication and persistent jobs. No source module copied. |
| [AutoShorts](https://github.com/shubhxtech/AutoShorts/tree/72d7f4e8bfb763f3f6cf5647cbfafd2b14c76edd) | MIT, Copyright 2026 shubhxtech | Studied `render/edl.py`, `render/plan.py`, `render/audio.py`, `render/sfx.py`, `understand/signals.py` and dependency configuration. Equivalent validated edit decisions and restrained source-driven effects extend the existing renderer. No source module or bundled asset copied. |

Both MIT licenses permit commercial use/modification/distribution subject to retaining their copyright and permission notices in copies/substantial portions. We do not install either independent application. Chopify's downloader was not copied; optional URL import uses the separately installed yt-dlp Python package. AutoShorts' MLX/macOS paths, Torch alignment, faceless generation, social automation and asset bundle are not imported: they add hardware/dependency/rights requirements outside this pipeline. Their heuristic success-language is not evidence that a game event or viral outcome occurred.

## Selected runtime components

| Component | License / obligations | Use |
|---|---|---|
| Ollama executable | [MIT](https://github.com/ollama/ollama/blob/main/LICENSE); retain notices if redistributing | Separately installed local server |
| Qwen3-VL-4B-Instruct | [Apache-2.0 model card](https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct); retain license/notices and identify modifications if redistributing | User-downloaded weights; not committed or bundled |
| Whisper base / converted Faster-whisper base | [MIT model card](https://huggingface.co/Systran/faster-whisper-base); retain notices | Cached user-downloaded model |
| Faster-whisper, CTranslate2 | MIT; retain copyright/license | CPU int8 speech inference |
| PySceneDetect | BSD-3-Clause; retain notices, no endorsement | Actual scene boundaries |
| OpenCV | Apache-2.0 for current OpenCV; bundled third-party notices also apply | Small frame measurements |
| NumPy | BSD-3-Clause with bundled dependency notices | Audio/frame arithmetic |
| PyAV | BSD-3-Clause wrapper; linked FFmpeg terms apply separately | Transitive speech dependency; native decoding uses safe FFmpeg |
| pypdf | BSD-3-Clause | Local campaign PDF text |
| yt-dlp 2026.10.26 | Unlicense for the Python package; bundled executables and dependencies can carry additional terms | Optional authorized public YouTube import; installed locally, no executable bundled |
| FastAPI, SQLAlchemy, Alembic, httpx, Pydantic, React, Next.js | MIT (retain notices); dependencies have separate licenses | Existing app/API/storage |
| cryptography | Apache-2.0 OR BSD-3-Clause, bundled OpenSSL/Rust notices | Existing encrypted OAuth tokens |
| Tesseract (optional) | Apache-2.0; language data licenses must be retained | Separately installed local OCR |
| FFmpeg / ffprobe | [Build-dependent LGPL-2.1-or-later or GPL](https://ffmpeg.org/legal.html); nonfree builds are not redistributable | Separate process; existing x264-enabled binaries are GPL builds |
| FFmpeg WASM core | GPL-2.0-or-later; exact corresponding source/build obligations apply on redistribution | Existing browser engine, separate from native model processing |
| FFmpeg WASM wrapper | MIT | Existing browser worker adapter |
| Noto Sans | SIL OFL-1.1; retain OFL, do not sell font alone or misuse reserved names | Existing browser font with packaged notice |

Commercial use is not prohibited by these selected licenses, but redistribution obligations still apply. Running a separately installed FFmpeg process is different from distributing its binary or linking its libraries. Before shipping a binary installer/container/WASM bundle, preserve all notices, inspect the exact `ffmpeg -buildconf`, provide exact corresponding FFmpeg/x264 source and build instructions as required, and exclude `--enable-nonfree` builds. A generic upstream link alone does not establish full GPL binary-distribution compliance. Codec patents and rights in input/output footage are separate questions. This source upgrade is not a certification of downstream binary-distribution compliance.

`scripts/license-inventory.py` records installed Python versions, declared licenses and license-file paths in `docs/python-license-inventory.json`; it is an inventory, not an automatic license approval. The frontend lockfile pins resolved dependencies; their installed `LICENSE`/`NOTICE` files must accompany redistribution. Existing browser notices are emitted by `frontend/scripts/prepare-browser.mjs`. No music, commercial sound packs, reference audiovisual content, pretrained face/game detector, or unlicensed font is added. New synthetic/user-supplied effects must retain provenance. Future dependencies/models need their own review rather than inheriting a repository's MIT label.
