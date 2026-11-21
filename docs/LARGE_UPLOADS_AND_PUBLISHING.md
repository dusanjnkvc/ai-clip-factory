# Large uploads and automatic publishing text

November 21, 2026.

Video uploads accept up to 1,500 × 1,024 × 1,024 bytes (1,572,864,000 bytes). The browser's old 150 MB upload gate and 250 MB combined render gate are now 1,500 MB. Native defaults and the example environment also use 1,500 MB; the Next.js proxy allows 1,600 MB to accommodate the request envelope. Existing operator overrides remain configurable.

For large sources, FFmpeg reads the original Blob through WORKERFS. Only a small header is read to validate the container signature; the entire source is not copied into JavaScript and then the WebAssembly heap. Mounts are released after rendering. The combined sources for a single browser export remain bounded to 1,500 MB. Browser storage, decoding and output memory still depend on the device.

Create Clips automatically proposes three titles, a publication caption, relevant hashtags and an opening headline. The recommended option is used if the user simply clicks Generate. Writing any publishing text is optional. An optional editor starts from the app's proposed copy. Required campaign hashtags/mentions lead the caption, required disclosures remain, and mandatory on-video wording is retained. The clip editor also offers **Suggest titles, captions & hashtags**, creating a metadata version while retaining the actual rendered video and edit plan.

The free browser edition uses editorial templates grounded in source filenames and supplied subtitle cues overlapping the selected range. It does not infer game events, transcribe speech, retrieve live trends, calculate a viral score or promise views. Unknown footage receives a broad draft rather than invented claims. The native edition retains its existing local-model metadata generation. No paid provider or account is required by this change.

Validation: 63 browser/API/creative/real-WASM checks and the 18 relevant backend API tests passed. The size-gate test covers the exact maximum and rejects the next byte. The API test generates three distinct titles with no supplied publishing text, excludes out-of-range dialogue, retains required tags/mentions, and checks that regenerating metadata preserves the video and plan. Production build/type checking passed.

Actual browser acceptance used a generated 3-second audiovisual source padded with a valid MP4 `free` box to exactly 1,500 MB. The UI accepted/stored it and exported an actual 1.8-second Remotion clip via the large-file WORKERFS path without any manually entered title, caption, tags or headline. Required campaign wording and the automatic opening headline were visible. A metadata-only regeneration created v2 with new proposed copy. This validates the file-size boundary and read path, not every possible long/complex source or gaming editorial quality.

Local test output: `C:\Users\duled\Downloads\clip-f2346f06.mp4`. Owned generated inputs and screenshots are under ignored `.runtime/upload-acceptance/`. No user footage, models, credentials or large test media is committed.
