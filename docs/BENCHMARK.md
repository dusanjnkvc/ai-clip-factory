# Performance and media validation

The targets are a publish-ready first clip under 5 minutes, three clips under 10 minutes, and five clips under 15 minutes under defined benchmark conditions. These are engineering goals. Rendering a short generated fixture or passing mocked-provider tests does not demonstrate those targets for campaign media.

## End-to-end benchmark

Use a configured deployment, an authorized representative video, real hosted AI credentials, and a real campaign brief. Keep a record of source duration, file size, codec, resolution, speech language, content type, clip length/count, AI models, cloud region, CPU/RAM allocation, storage type, queue depth, and whether workers/transcripts are warm or cold. Do not mix cached and uncached runs in one average.

1. Create an account in the running application. Import and analyze the brief. Review ambiguous or contradictory rules; do not remove genuine campaign requirements to obtain PASS.
2. Upload authorized source media, record the upload time separately, and confirm the media rights. Obtain the campaign and source IDs from their API responses in the browser's developer tools.
3. Run the measurement helper with the same account. It creates a real paid generation job and polls persisted job and clip records. The password is requested using a hidden prompt.

```powershell
.\.venv\Scripts\python.exe scripts\benchmark.py --email you@example.com --campaign-id CAMPAIGN_ID --source-id SOURCE_ID --clips 3 --mode fast --download-first
```

For direct API access, use `--base-url http://localhost:8000 --origin http://localhost:3000`. The default frontend URL is `http://localhost:3000`. For a deployed app, use its HTTPS URL. `BENCHMARK_PASSWORD` can supply the password in CI from a secret store; do not put it in command-line arguments or commit it.

The helper distinguishes:

- **First rendered:** an actual MP4 exists; compliance may still require review.
- **First compliant:** a rendered clip has a PASS result. Semantic review cannot be skipped to improve the measurement.
- **Three/five compliant:** enough individual PASS clips are visible; the first does not wait for the batch.
- **Worker first-clip time:** time recorded by the worker, excluding any preceding queue wait. Client measurements include queue wait.

Measurement begins immediately before the generation request. It includes transcription, planning, rendering, metadata, and compliance. Campaign analysis and source upload happen before this request and must be reported separately. Polling introduces up to the polling interval of uncertainty; default is two seconds. A blocked/failed job or a batch with no PASS clip does not meet the publish-ready target.

With `--download-first`, the helper downloads the first real clip, inspects its media streams, and fully decodes it through FFmpeg. It records the media inspection and timing JSON under ignored `.runtime/benchmarks/`. The report contains no password, session cookie, or signed download URL. Verify the vertical dimensions, H.264/AAC stream, subtitle timing/readability, relevant framing, content context, required disclosures, and audio quality by watching the result as well.

Run at least five cold and five warm trials for each representative media category. Report individual values and median/p95 separately, including unsuccessful trials and the sample size. Track actual billed provider and CPU/storage expenses alongside application estimates. A narrow trial set cannot establish general content quality or viral performance.

## Rendering regression test

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m pytest tests/test_pipeline.py -q
Pop-Location
```

The FFmpeg regression uses synthetic video/audio test signals generated locally. They are technical fixtures with no third-party footage or license requirement. Real rendering, full decode, vertical output, subtitle timing, and input validation are checked where supported by the installed FFmpeg build. Hosted-provider substitutes in other tests validate request/response logic only.

## Publishing and submissions

Run publication tests separately with a channel and media authorized for the test. Confirm OAuth scope, explicit approval, account eligibility, actual published URL/timestamp, duplicate prevention, retries, and failure handling. A provider sandbox or mocked upload is not production upload verification.

For a campaign with a submission window, verify the countdown begins at the actual publication timestamp. Check the 15/10/5-minute warning boundaries and the manual submission handoff. A rendered or uploaded clip must never be counted as a confirmed campaign submission.
