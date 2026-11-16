# Native local rendering benchmark

This helper targets the optional Python API/worker edition, not the static GitHub Pages/browser edition. Browser FFmpeg must be measured in the actual tab/device and may stop when the tab closes; native timings do not establish browser performance.

The default benchmark measures one user-selected clip through the real local worker, FFmpeg render, metadata/compliance persistence, and optional download/full decode. It does not call an AI provider in `FREE_MODE=true`, and refuses a hosted-mode server unless `--allow-hosted` is explicitly supplied. No service fee is required for this local path; your computer still uses CPU, electricity, and disk.

## Prepare the records

1. Run the local application, create an account, and save/review a real campaign brief. Unknown semantic rules must stay review items until supported by evidence.
2. Upload a representative video that you are authorized to edit and republish. Obtain the campaign/source IDs from their API responses in browser developer tools.
3. Choose a source range. Optionally prepare an SRT/VTT whose cue times refer to the original source. Its upload happens before the render timer.
4. Run the helper. The free native workspace requires no login:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark.py --campaign-id CAMPAIGN_ID --source-id SOURCE_ID --start 10 --end 30 --title "User-selected test clip" --download-first
```

For source-timed captions, add `--subtitles-file 'C:\path\captions.srt'`. To measure the available source beginning capped at 30 seconds, omit `--start` and `--end`. The range is a manual/default choice, not a detected highlight. Free mode accepts one clip per benchmark job.

For direct API access use `--base-url http://localhost:8000 --origin http://localhost:3000`. The default base URL is `http://localhost:3000`. The default free local API requires no authentication. For a separately configured authenticated native server, `--email` enables a hidden password prompt; `BENCHMARK_PASSWORD` may supply it through an environment secret. Do not put passwords in command-line arguments or Git.

## Interpret the output

The report distinguishes:

- **First rendered:** a real MP4 exists, even if semantic review remains required.
- **First compliant:** a rendered clip has PASS. Do not erase real rules or skip required review to improve timing.
- **Worker first-clip time:** elapsed time saved by the worker, excluding earlier queue wait. The client measurement includes that wait.
- **Download verified:** the first rendered MP4 was downloaded, inspected, and fully decoded by FFmpeg after timing.

Measurement begins before `POST /api/jobs`. Campaign review, source upload, and optional subtitle upload happen first and must be reported separately. The default poll interval adds up to two seconds of observation uncertainty. A blocked/failed job or a REVIEW_REQUIRED result does not meet a publish-ready target.

Reports and optional MP4s are saved under ignored `.runtime/benchmarks/`. No password, session cookie, or signed download URL is included. Watch the output as well: check framing, source context, subtitle readability and synchronization, disclosure/branding requirements, and sound. A full decode proves playability, not editorial quality or campaign approval.

Record source duration/codec/resolution, selected output duration, CPU/RAM, disk type, caption format, queue depth, and warm/cold state. Report individual trials and median/p95 with failures included. A short synthetic fixture does not establish performance for an hour-long source. The original under-5/10/15-minute targets for one/three/five AI-created compliant clips remain unverified engineering goals; the free local benchmark has different scope.

## Rendering regression tests

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m pytest tests/test_pipeline.py tests/test_free_services.py -q
Pop-Location
```

Tests use generated video/audio signals without third-party footage. Actual H.264/AAC rendering, full decode, vertical output, input restrictions, and caption behavior are checked where supported by FFmpeg. Remote-provider substitutes only test adapter behavior; they do not establish live access or permission.

## Optional hosted benchmark

Only if you deliberately enable `FREE_MODE=false`, supply hosted credentials and positive spending limits, and accept possible provider charges, use `--allow-hosted`. The existing `--clips 3`/`--clips 5` options then measure individual compliance milestones. This is outside the no-service-fee workflow. Never assume that an API key, promotional balance, or cloud free tier guarantees no charges.

## Manual publishing and submissions

Free mode provides upload packages, not direct external publishing. Publish using an authorized platform account and record the actual public URL/time. For a campaign with a submission window, confirm the countdown begins at that actual timestamp and verify the 15/10/5-minute warning boundaries. Publication and confirmed campaign submission remain separate records.
