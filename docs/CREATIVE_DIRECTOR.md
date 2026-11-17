# Creative Director: free assisted editing

Open the [browser app](https://dusanjnkvc.github.io/ai-clip-factory/) and select **AI Creative Director**. This feature runs in the static browser edition; the optional native Python edition retains its existing manual clipping workflow.

No account, API key, subscription, language model, or paid service is needed. The semantic AI provider is explicitly unavailable. The feature proposes editing choices from local measurements and supplied text, and keeps the editor responsible for the meaning of the footage.

## Prepare a source and campaign

Import a video through **Create Clips** and record permission to edit and republish it. Review the campaign rules before using a campaign source. Supply source-timed SRT/VTT captions if you want speech captions. Without supplied cues, there is no transcription or invented dialogue.

Select the source and campaign in Creative Director. Choose duration, pace, audience, style, and output resolution, then analyze and create concepts. Source ranges must refer to the actual imported file. A public video URL does not establish reuse permission.

The analyzer decodes up to 24 representative video frames. It measures frame differences, brightness, edge detail, and a low-confidence visual centroid for crop hints. Candidate scene changes are approximate sampled boundaries, not frame-accurate scene detection. Motion is a frame-difference proxy; the app does not track a person, face, object, or game event.

For sources within the bounded audio size/duration limits, the browser attempts local audio decoding and RMS loudness measurement. Unsupported containers, unavailable decoding, or larger media leave audio analysis unavailable. Loudness does not establish a meaningful event. Analysis displays these limits and source-quality warnings instead of substituting inferred facts.

## Compare concepts and edit

The proposed concepts differ in actual source selection, pacing, and story structure:

- **High Engagement** uses a compact source window with cuts around measured changes. The label is a proposed editing approach, not a performance claim.
- **Cinematic** favors a different source window with sustained shots and restrained transitions.
- **Creative Storytelling** combines chronological earlier, middle, and later excerpts. A person must verify that the resulting context and conclusion are truthful.

The generator can return fewer than three concepts when the source cannot support meaningful alternatives. It explains unavailable options. It does not create duplicate concepts merely to fill three cards, nor create missing footage or outcomes.

The hook assessment explains clarity, curiosity, visual signals, relevance, readability, and accuracy heuristics. Caption quotations are grounded in supplied cues; those cues still need authenticity and context review. The score is not trained retention prediction, semantic verification, or a promise of views.

Use actual source previews to inspect the proposal. The storyboard supports source times, ordering, shot roles, crop position and endpoint motion, zoom, composition, transitions, effects, and editor-written overlays. Edit the hook, title, description, hashtags, and captions. Locks protect shot decisions; undo/redo works within the current editing session. Saved projects keep their drafts in IndexedDB. Regeneration preserves saved work and creates another proposal; browser storage is not a backup.

History comparisons flag repeated source openings, overlapping footage, narrative patterns, composition, and hooks. A similarity warning is a local overlap heuristic, not an originality or platform-policy verdict.

## Styles and rendering

The eight styles are Cinematic Gaming, High-Energy Action, Kinetic Typography, Reaction / Split Screen, Interactive Tutorial, Comparison / VS, Retro Arcade, and Minimal Premium. Styles configure supported pacing, composition, caption treatment, transitions, and restrained effects. Their genre names do not mean the app recognized that genre in the source.

Real FFmpeg WebAssembly rendering supports:

- 1080 × 1920, 720 × 1280, or 540 × 960 H.264/AAC MP4 output.
- Vertical fill crops with bounded manual crop motion and zoom.
- Full source composition over a source-derived blurred background, or split composition with separately supplied footage.
- Cuts, short shot fades, contrast/retro treatments, source audio normalization, or mute.
- Supplied cue captions with size, color, position, safe margins, and none/fade/pop/slide animation.

Caption animation is cue-level. The workflow does not infer word alignment, synthesize narration, add music, create reactions, or invent dialogue. Fades are shot fades rather than overlapping crossfades. Secondary split footage uses primary-source audio; it does not mix a second soundtrack. A larger export can upscale source pixels without restoring detail. Review the actual render for legibility, framing, audio, and source quality.

**Fast Export** uses quicker CPU encoding. **Premium Export** uses a slower encoding preset and lower compression target; it is a quality setting with no paid tier. Both run on the current device. A successful render is probed and fully decoded before the output is stored. Keep the tab open, allow enough memory, and start with short sources when checking a device.

## Campaign checks and original footage

Campaign rules can classify mandatory, prohibited, recommended, and unclear requirements. Deterministic preflight blocks missing sources, invalid timestamps, unavailable split footage, invalid crop/effect parameters, unsupported sizes, and supplied duration violations.

For a campaign that prohibits automated clipping or AI-generated content, the app requires an editor's manual decision note before rendering. Recording a note is not evidence that the campaign permits an assisted workflow. That question remains for human review against the original terms.

If original creator footage is required, import authorized original footage with its rights note **and use it in a storyboard shot or split composition**. Merely importing a file does not satisfy the check. The declaration records the user's evidence; the app cannot independently prove authorship or suitability. Split styles also need an actual separate source with enough duration for the requested shot.

Branding, prohibited content, audience restrictions, source music, source claims, AI-voice restrictions, and draft approval remain evidence-backed human review tasks. No green render status converts those semantic checks to approved. Creative Director plans remain `local_assisted`, provider `not_configured`, and `publish_ready: false`.

## Publishing assistant

Choose Shorts, TikTok, or Reels to format source/editor-grounded title and caption options, required campaign mentions/disclosures/links, hashtags, and a suggested real source cover timestamp. Text may repeat when there is insufficient supplied wording; the assistant does not fabricate a claim to create variety.

Edit and inspect the text before posting. Copying a suggestion does not publish, schedule, submit, establish platform eligibility, or predict performance. Download the actual MP4 and manual package, upload through your authorized platform account, and record the actual URL and publication time. Campaign submission is a separate manual step.

## Local state and tests

Sources, measured thumbnails, projects, versions, and outputs stay in the current browser profile's IndexedDB. The repository and GitHub Pages contain public application files, not user video uploads. Storage can be lost through clearing, eviction, private browsing, or changing profiles/devices. Preserve originals and download important results elsewhere.

From `frontend/`:

```sh
node --test scripts/test-browser.mjs scripts/test-browser-api.mjs scripts/test-creative.mjs
npm run build:pages
node --test scripts/test-wasm.mjs
```

The WASM integration test requires the font/assets supplied by browser preparation. It exercises the real packaged core and production renderer in a Node worker-shaped host. That verifies actual encoding/decoding behavior; browser UI, media decoding, IndexedDB, and deployment are separate checks recorded in [status](STATUS.md).

The API regression suite runs the production local API and rules against in-memory persistence and a controlled media adapter. It verifies project drafts, actual render-setting preflight, manual-decision and source requirements, worker revalidation, and export gating. Actual encoding remains covered separately by the WASM tests.
