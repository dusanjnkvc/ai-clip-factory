# Unified creation redesign — reference inspection

Reference files were explicitly identified by the user in Downloads. Originals were only read.

| Property | Opus example.mp4 | clip-8a2afc5d-8b79-4fae-8813-038d71adc5fa.mp4 |
|---|---|---|
| Duration | 45.0 seconds | 1.83 seconds |
| Dimensions | 1080 × 1920 | 1080 × 1920 |
| Frame rate | 30 FPS | 30 FPS |
| Codecs | H.264 / AAC | H.264 / AAC |
| Sampled content | Snake gameplay fills the portrait canvas | Synthetic color/test pattern |
| Headline | Compact upper white panel with bold dark type at opening | Small “Local render verification” near lower edge |

Decoded samples were inspected at 0.5/10/22/40 seconds in the Opus reference and 0.1/0.5/1/1.5 seconds in the app example. Contact sheet: ignored `.runtime/redesign-reference/comparison.jpg` (Opus on top). The supplied app example is a rendering fixture, not gaming footage; it cannot establish quality differences in combat selection, narration or narrative pacing. No synthetic fixture is counted as semantic gaming acceptance.

The Opus sample already contains portrait gameplay and visible OpusClip branding. That branding remains untouched. Its useful presentation traits are prominent undistorted gameplay, a short legible opening headline and restrained treatment. It does not demonstrate that blur or repeated visual effects improve every source. The reusable native template preserves portrait sources and fits wide gameplay over synchronized enlarged Gaussian-blurred/darkened source footage. Output now defaults to 30 FPS with a validated 60 FPS plan option. No application logo, watermark or ending screen is inserted. Campaign-required text remains a separate requirement.

Implementation is on `codex/unified-creation`. Both editions expose five main sections; the native shell provides automatic local creation and inline editing while the browser edition retains free manual processing and measured concepts. Stored tables and legacy outputs remain available. See [delivery evidence and limitations](REDESIGN_DELIVERY.md). Actual renders and UI checks do not establish Opus-level editorial parity or live social integration readiness.
