import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";

// The rules module has only a type import. Transpilation removes it so the
// browser-independent safety boundaries can run without a DOM or test framework.
const source = await readFile(new URL("../lib/browser-rules.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
});
const engine = await import("data:text/javascript;base64," + Buffer.from(compiled.outputText).toString("base64"));
const { emptyRules, validateRules, extractRules, manualPlan, validatePlan, manualMetadata, validateMetadata, compliance } = engine;

function campaign(overrides = {}) {
  return validateRules({
    ...emptyRules(),
    allowed_platforms: ["youtube"],
    draft_approval_required: false,
    evidence: [{ field: "allowed_platforms", quote: "Platforms: YouTube", source: "brief" }],
    ...overrides,
  });
}
function video(overrides = {}) {
  return { filename: "owned-source.mp4", media_info: { duration: 60 }, ...overrides };
}
function plan(overrides = {}, rules = campaign()) {
  return manualPlan({
    start: 5, end: 15, title: "The selected source moment",
    description: "A description supplied by the person editing.",
    hashtags: ["#owned"], crop_x: .5, crop_y: .5, zoom: 1,
    ...overrides,
  }, video(), rules, []);
}
function rendered(overrides = {}) {
  return { duration: 10, width: 1080, height: 1920, codec: "h264", has_audio: true, decode_verified: true, subtitle_synchronized: true, ...overrides };
}
function check(result, rule) {
  const item = result.checks.find(item => item.rule === rule);
  assert.ok(item, "Expected a compliance result for " + rule);
  return item;
}
function evaluate({ rules = campaign(), clip = plan(), metadata = manualMetadata(clip, campaign()), media = rendered(), evidence = {}, draftApproved = false } = {}) {
  return compliance(clip, metadata, rules, media, true, evidence, draftApproved);
}

test("labeled extraction retains exact source evidence and leaves unsupported rules unknown", () => {
  const brief = "Platforms: YouTube Shorts, TikTok\nDuration: 12–35 seconds\nHashtags: #owned #ad\nDraft approval: required\nSubmission window: 30 minutes";
  const rules = extractRules(brief, "Authorized campaign");
  assert.deepEqual(rules.allowed_platforms, ["youtube", "tiktok"]);
  assert.equal(rules.min_duration, 12);
  assert.equal(rules.max_duration, 35);
  assert.deepEqual(rules.required_hashtags, ["#owned", "#ad"]);
  assert.equal(rules.draft_approval_required, true);
  assert.equal(rules.submission_window_minutes, 30);
  assert.equal(rules.reward_per_1000, null);
  assert.equal(rules.maximum_payout, null);
  assert.ok(rules.uncertainties.length, "Limited local extraction must still require review.");
  assert.ok(rules.evidence.length >= 5);
  for (const evidence of rules.evidence) {
    assert.ok(brief.includes(evidence.quote), "Every quote must occur in the supplied brief.");
    assert.equal(evidence.source, "brief");
  }
});

test("incidental prose does not become platform permission or draft approval", () => {
  const rules = extractRules("We enjoyed some TikTok clips. Maybe post a short video with #ad. Ask the owner about approval.", "Unclear campaign");
  assert.deepEqual(rules.allowed_platforms, []);
  assert.deepEqual(rules.required_hashtags, []);
  assert.equal(rules.draft_approval_required, null);
  assert.equal(rules.min_duration, null);
});

test("contradictory campaign instructions remain flagged instead of silently replacing the first rule", () => {
  const rules = extractRules("Platforms: YouTube\nPlatforms: TikTok\nDuration: 30–10 seconds", "Conflicting brief");
  assert.deepEqual(rules.allowed_platforms, ["youtube"]);
  assert.ok(rules.contradictions.some(value => value.includes("allowed_platforms")));
  assert.ok(rules.contradictions.some(value => /duration/i.test(value)));
});

test("manual campaign input rejects malformed lists, unsupported platforms, and non-finite values", () => {
  for (const supplied of [
    { required_hashtags: "#ad" },
    { allowed_platforms: ["unrecognized-service"] },
    { min_duration: Number.NaN },
    { maximum_payout: Number.POSITIVE_INFINITY },
    { draft_approval_required: "probably" },
  ]) assert.throws(() => validateRules(supplied), Error);
});

test("the default manual range respects source length and uses only overlapping caption cues", () => {
  const selected = manualPlan({ start: 3, end: null, title: "Human-selected range" }, video({ media_info: { duration: 20 } }), campaign(), [
    { start: 0, end: 2, text: "Not in this clip." },
    { start: 4, end: 5, text: "Actually selected speech." },
  ]);
  assert.equal(selected.start, 3);
  assert.equal(selected.end, 20);
  assert.equal(selected.transcript_excerpt, "Actually selected speech.");
  assert.equal(selected.generation_method, "manual_local");
  assert.equal(selected.score_origin, "not_scored");
  assert.equal(selected.scenes[0].start, 3);
  assert.equal(selected.scenes[0].end, 20);
});

test("manual selection rejects reversed, negative, non-finite, too-short, and out-of-source ranges", () => {
  for (const selection of [
    { start: 15, end: 5 },
    { start: -1, end: 5 },
    { start: 5, end: 61 },
    { start: 5, end: 5.5 },
    { start: 5, end: Number.POSITIVE_INFINITY },
    { start: 59, end: null },
  ]) {
    // A one-second terminal clip is valid; its explicit boundary is checked below.
    if (selection.start === 59) continue;
    assert.throws(() => plan(selection), Error);
  }
  assert.equal(plan({ start: 59, end: null }).end, 60);
});

test("out-of-frame crop positions and unsafe zoom values are rejected", () => {
  for (const selection of [
    { crop_x: -0.01 }, { crop_x: 1.01 }, { crop_y: -1 },
    { crop_y: Number.NaN }, { zoom: .99 }, { zoom: 1.51 },
  ]) assert.throws(() => plan(selection), Error);
});

test("an edited timeline cannot introduce scenes outside the approved source selection", () => {
  const approved = plan();
  assert.throws(() => validatePlan({ ...approved, scenes: [] }, 60), Error);
  assert.throws(() => validatePlan({ ...approved, scenes: [{ ...approved.scenes[0], start: 4 }] }, 60), Error);
  assert.throws(() => validatePlan({ ...approved, scenes: [{ ...approved.scenes[0], end: 16 }] }, 60), Error);
  assert.throws(() => validatePlan({ ...approved, scenes: Array.from({ length: 21 }, () => ({ ...approved.scenes[0] })) }, 60), Error);
});

test("metadata stays deterministic and human-authored without claiming an AI score", () => {
  const rules = campaign({ required_hashtags: ["#ad"], required_mentions: ["@campaign"], required_disclosures: ["Paid partnership."] });
  const clip = plan({ title: "My exact title", description: "My exact description." }, rules);
  const first = manualMetadata(clip, rules);
  assert.deepEqual(first, manualMetadata(clip, rules));
  for (const platform of ["youtube", "tiktok", "instagram"]) {
    const selected = first[platform].variants[first[platform].recommended_index];
    assert.equal(selected.title, "My exact title");
    assert.ok(selected.description.startsWith("My exact description."));
    assert.ok(selected.description.includes("@campaign"));
    assert.ok(selected.description.includes("Paid partnership."));
    assert.ok(selected.hashtags.includes("#ad"));
    assert.equal(selected.score, 0);
    assert.match(selected.reasoning, /not AI generated|not.*scored/i);
  }
  const invalid = structuredClone(first);
  invalid.youtube.variants[0].title = "x".repeat(101);
  assert.throws(() => validateMetadata(invalid), Error);
});

test("a longer hashtag cannot satisfy a shorter required campaign hashtag", () => {
  const clip = plan({ hashtags: ["#advertisement"] });
  const result = evaluate({ clip, metadata: manualMetadata(clip, campaign()), rules: campaign({ required_hashtags: ["#ad"] }) });
  assert.equal(check(result, "metadata_youtube").status, "FAIL");
  assert.equal(result.publish_ready, false);
});

test("mentions require a whole account token while campaign tags remain case-insensitive", () => {
  const clip = plan({ description: "Visit @branding for details.", hashtags: ["#AD"] });
  const metadata = manualMetadata(clip, campaign());
  const missingMention = evaluate({ clip, metadata, rules: campaign({ required_mentions: ["@brand"] }) });
  assert.equal(check(missingMention, "metadata_youtube").status, "FAIL");
  const exactTag = evaluate({ clip, metadata, rules: campaign({ required_hashtags: ["#ad"] }) });
  assert.equal(check(exactTag, "metadata_youtube").status, "PASS");
});

test("semantic campaign requirements never pass from text or incomplete reviewer evidence alone", () => {
  const rules = campaign({ required_branding: ["Show the authorized campaign logo."], prohibited_content: ["No misleading context."], audio_restrictions: ["No unlicensed music."] });
  const noEvidence = evaluate({ rules });
  for (const rule of ["branding", "content_restrictions", "audio_restrictions"]) assert.equal(check(noEvidence, rule).status, "REVIEW_REQUIRED");
  assert.equal(noEvidence.publish_ready, false);
  const inadequate = evaluate({ rules, evidence: { branding: { confirmed: true, note: "Looks fine" } } });
  assert.equal(check(inadequate, "branding").status, "REVIEW_REQUIRED");
});

test("draft pre-approval remains blocking until its separate confirmation is supplied", () => {
  const rules = campaign({ draft_approval_required: true });
  assert.equal(check(evaluate({ rules }), "draft_approval").status, "REVIEW_REQUIRED");
  assert.equal(check(evaluate({ rules, draftApproved: true }), "draft_approval").status, "PASS");
});

test("duration violations and unknown measurements cannot pass deterministic checks", () => {
  const rules = campaign({ min_duration: 8, max_duration: 12 });
  assert.equal(check(evaluate({ rules, media: rendered({ duration: 7 }) }), "duration").status, "FAIL");
  assert.equal(check(evaluate({ rules, media: rendered({ duration: 13 }) }), "duration").status, "FAIL");
  assert.notEqual(check(evaluate({ media: rendered({ duration: Number.NaN }) }), "duration").status, "PASS");
});

test("wrong resolution, wrong codec, missing audio, or an unverified decode blocks publication", () => {
  for (const media of [
    rendered({ width: 720, height: 1280 }),
    rendered({ codec: "vp9" }),
    rendered({ has_audio: false }),
    rendered({ decode_verified: false }),
  ]) {
    const result = evaluate({ media });
    assert.equal(check(result, "video_format").status, "FAIL");
    assert.equal(result.publish_ready, false);
  }
});
