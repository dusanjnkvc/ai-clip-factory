/** Conservative local parsing and human review. These helpers make no AI calls. */
import type { BrowserRow } from "./browser-db";

export const PLATFORMS = ["youtube", "tiktok", "instagram"];
const MAX_CAPTIONS = 10000;
function containsRequiredToken(text: string, value: string): boolean {
  const escaped = value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(^|[^\\p{L}\\p{N}_])${escaped}(?=$|[^\\p{L}\\p{N}_])`, 'iu').test(text);
}

export function emptyRules(): BrowserRow {
  return { campaign_name: "Untitled campaign", campaign_type: "unknown", allowed_platforms: [], min_duration: null, max_duration: null, required_hashtags: [], required_mentions: [], required_disclosures: [], required_branding: [], permitted_source_material: [], prohibited_content: [], audio_restrictions: [], minimum_views: null, reward_per_1000: null, flat_fee: null, maximum_payout: null, currency: null, draft_approval_required: null, submission_deadline: null, submission_window_minutes: null, submission_instructions: null, submission_url: null, evidence: [], uncertainties: [], contradictions: [] };
}

export function validateRules(supplied: BrowserRow): BrowserRow {
  if (!supplied || typeof supplied !== "object" || Array.isArray(supplied)) throw new Error("Campaign rules must be an object.");
  const rules = { ...emptyRules(), ...structuredClone(supplied) };
  for (const field of ["allowed_platforms", "required_hashtags", "required_mentions", "required_disclosures", "required_branding", "permitted_source_material", "prohibited_content", "audio_restrictions", "uncertainties", "contradictions", "evidence"]) {
    if (!Array.isArray(rules[field])) throw new Error(`${field} must be a list.`);
    if (field !== "evidence" && rules[field].some((value: unknown) => typeof value !== "string")) throw new Error(`${field} must contain text values.`);
  }
  if (rules.allowed_platforms.some((platform: string) => !PLATFORMS.includes(platform))) throw new Error("Use youtube, tiktok, or instagram as permitted platforms.");
  for (const field of ["min_duration", "max_duration", "minimum_views", "reward_per_1000", "flat_fee", "maximum_payout", "submission_window_minutes"]) {
    if (rules[field] !== null && (!Number.isFinite(rules[field]) || rules[field] < 0)) throw new Error(`${field} must be a nonnegative number or null.`);
  }
  if (rules.draft_approval_required !== null && typeof rules.draft_approval_required !== "boolean") throw new Error("Draft approval must be true, false, or unknown.");
  if (rules.submission_url != null) {
    try { const url = new URL(rules.submission_url); if (url.protocol !== 'https:' || url.username || url.password) throw new Error(); }
    catch { throw new Error('A campaign submission link must use HTTPS without embedded credentials.'); }
  }
  return rules;
}

export function extractRules(brief: string, name: string): BrowserRow {
  const rules = emptyRules(); rules.campaign_name = name;
  rules.uncertainties = ["Local text extraction is limited. Review the original campaign and every rule before publication."];
  const mapping: BrowserRow = { youtube: "youtube", "youtube shorts": "youtube", shorts: "youtube", tiktok: "tiktok", instagram: "instagram", "instagram reels": "instagram", reels: "instagram" };
  const seen: BrowserRow = {};
  function assign(field: string, value: unknown, line: string) {
    if (field in seen && JSON.stringify(seen[field]) !== JSON.stringify(value)) { rules.contradictions.push(`Conflicting supplied values for ${field}.`); return; }
    seen[field] = value; rules[field] = value; rules.evidence.push({ field, quote: line, source: "brief", verified_quote: true, extraction_method: "labeled_text" });
  }
  for (const line of brief.split(/\r?\n/).map(line => line.trim())) {
    let match = line.match(/^(?:(?:allowed|permitted)\s+)?platforms?\s*:\s*(.+)$/i);
    if (match) { const values = match[1].replace(/\.$/, "").split(/\s*[,;/|]\s*/).map(value => mapping[value.toLowerCase()]); if (values.length && values.every(Boolean)) assign("allowed_platforms", [...new Set(values)], line); }
    match = line.match(/^(?:required\s+)?hashtags?\s*:\s*((?:#[\p{L}\p{N}_]+[ ,]*)+)$/iu);
    if (match) assign("required_hashtags", [...new Set(match[1].match(/#[\p{L}\p{N}_]+/gu))], line);
    match = line.match(/^(?:clip\s+)?duration\s*:\s*(\d+(?:\.\d+)?)\s*[-–—]\s*(\d+(?:\.\d+)?)\s*(?:s|seconds?)\.?$/i);
    if (match) { assign("min_duration", Number(match[1]), line); assign("max_duration", Number(match[2]), line); }
    match = line.match(/^draft\s+(?:pre[- ]?)?approval\s*:\s*(required|not required|yes|no)\.?$/i);
    if (match) assign("draft_approval_required", ["yes", "required"].includes(match[1].toLowerCase()), line);
    match = line.match(/^submission\s+window\s*:\s*(\d+)\s*(?:m|min|minutes?)\.?$/i);
    if (match) assign("submission_window_minutes", Number(match[1]), line);
  }
  if (rules.min_duration !== null && rules.max_duration !== null && rules.min_duration > rules.max_duration) rules.contradictions.push("Minimum duration exceeds maximum duration.");
  return validateRules(rules);
}

export type CaptionCue = { start: number; end: number; text: string };
export function parseSubtitles(content: string, extension: string, sourceDuration: number): CaptionCue[] {
  const kind = extension.toLowerCase().replace(/^\./, "");
  if (!["srt", "vtt"].includes(kind)) throw new Error("Upload an SRT or VTT subtitle file.");
  const text = content.replace(/^\uFEFF/, "").replace(/\r\n?/g, "\n").trim();
  if (kind === "vtt" && !text.startsWith("WEBVTT")) throw new Error("VTT subtitles must start with WEBVTT.");
  if (text.includes("X-TIMESTAMP-MAP")) throw new Error("Export subtitle timestamps relative to the source video; timestamp maps are not supported.");
  function time(value: string): number {
    const matched = value.match(/^(?:(\d{2,}):)?(\d{2}):(\d{2})[,.](\d{3})$/);
    if (!matched || Number(matched[2]) >= 60 || Number(matched[3]) >= 60) throw new Error("Invalid subtitle cue timestamp.");
    return Number(matched[1] || 0) * 3600 + Number(matched[2]) * 60 + Number(matched[3]) + Number(matched[4]) / 1000;
  }
  const cues: CaptionCue[] = [];
  for (const block of text.split(/\n[ \t]*\n/)) {
    const lines = block.split("\n");
    if (/^(?:WEBVTT|NOTE|STYLE|REGION)(?:\s|$)/.test(lines[0])) continue;
    const timing = lines.map((line, index) => line.includes("-->") ? index : -1).filter(index => index >= 0);
    if (timing.length !== 1) throw new Error("Separate subtitle cues with blank lines and supply one timestamp line per cue.");
    const index = timing[0]; const bounds = lines[index].split("-->");
    if (bounds.length !== 2) throw new Error("Invalid subtitle cue bounds.");
    const start = time(bounds[0].trim()), end = time(bounds[1].trim().split(/\s+/)[0]);
    if (end <= start || end > sourceDuration + 0.05) throw new Error("Subtitle cues must have positive duration and fit inside the source video.");
    // Strip markup without constructing resource-bearing DOM nodes. Subtitle
    // markup must never cause an image/iframe/network request in this free mode.
    const entities: Record<string, string> = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ' };
    const visible = lines.slice(index + 1).join(' ').replace(/<[^>]*>/g, ' ').replace(/&(#x[0-9a-f]+|#\d+|amp|lt|gt|quot|apos|nbsp);/gi, (entity, name: string) => {
      if (name[0] !== '#') return entities[name.toLowerCase()] || entity;
      const code = name[1]?.toLowerCase() === 'x' ? parseInt(name.slice(2), 16) : Number(name.slice(1));
      return Number.isInteger(code) && code > 0 && code <= 0x10ffff && !(code >= 0xd800 && code <= 0xdfff) ? String.fromCodePoint(code) : '';
    }).replace(/\0/g, "").replace(/\s+/g, " ").trim();
    if (visible.length > 2000) throw new Error("Each subtitle cue may contain at most 2,000 characters.");
    if (visible) cues.push({ start, end, text: visible });
    if (cues.length > MAX_CAPTIONS) throw new Error("Subtitle files are limited to 10,000 cues.");
  }
  if (!cues.length) throw new Error("No timed subtitle cues were found.");
  return cues.sort((a, b) => a.start - b.start || a.end - b.end);
}

export function validatePlan(plan: BrowserRow, sourceDuration: number): BrowserRow {
  if (!Number.isFinite(plan.start) || !Number.isFinite(plan.end) || plan.start < 0 || plan.end <= plan.start || plan.end > sourceDuration + .001) throw new Error("Choose start and end times inside your source video.");
  if (!Array.isArray(plan.scenes) || !plan.scenes.length || plan.scenes.length > 20) throw new Error("An editing plan must have 1–20 source scenes.");
  let duration = 0;
  for (const scene of plan.scenes) {
    if (![scene.start, scene.end, scene.crop_x, scene.crop_y, scene.zoom].every(Number.isFinite) || scene.start < plan.start || scene.end > plan.end || scene.end <= scene.start) throw new Error("A scene is outside the selected source range.");
    if (scene.crop_x < 0 || scene.crop_x > 1 || scene.crop_y < 0 || scene.crop_y > 1 || scene.zoom < 1 || scene.zoom > 1.5) throw new Error("Use crop coordinates between 0 and 1 and zoom between 1 and 1.5.");
    duration += scene.end - scene.start;
  }
  if (duration < 1 || duration > 180) throw new Error("Browser clips must be between 1 and 180 seconds. Use a shorter range to limit browser memory use.");
  if (typeof plan.title !== "string" || !plan.title.trim() || plan.title.length > 100) throw new Error("A clip title of 1–100 characters is required.");
  return plan;
}

export function manualPlan(selection: BrowserRow, source: BrowserRow, rules: BrowserRow, cues: CaptionCue[]): BrowserRow {
  const start = Number(selection.start || 0), end = selection.end == null ? Math.min(source.media_info.duration, start + 30) : Number(selection.end);
  const title = String(selection.title || `${source.filename.replace(/\.[^.]+$/, "")} clip`).trim();
  const tags = selection.hashtags || [];
  if (!Array.isArray(tags) || tags.length > 30 || tags.some(tag => typeof tag !== "string" || !/^#[\p{L}\p{N}_]+$/u.test(tag))) throw new Error("Use up to 30 hashtags containing letters, numbers, or underscores.");
  const scene = { start, end, crop_x: Number(selection.crop_x ?? .5), crop_y: Number(selection.crop_y ?? .5), zoom: Number(selection.zoom ?? 1), rationale: "User-selected source range and framing." };
  const plan: BrowserRow = { title, start, end, scenes: [scene], hook: String(selection.hook || ""), show_hook: selection.show_hook === true, subtitle_style: selection.subtitle_style || "clean", subtitles_enabled: cues.length > 0, transcript_excerpt: cues.filter(cue => cue.end > start && cue.start < end).map(cue => cue.text).join(" "), content_type: "general", rationale: "Manual source selection; no AI analysis or ranking was performed.", generation_method: "manual_local", score_origin: "not_scored", semantic_notes: ["Review the actual video, context, framing, campaign rules, and permissions."], scores: { hook_strength: 0, engagement_potential: 0, clarity: 0, standalone_context: 0, campaign_relevance: 0 }, manual_metadata: { title, description: String(selection.description || ""), hashtags: [...new Set(tags)] }, edit_dna: { hook_structure: "User-selected opening", scene_order: "Original source order", cut_timing: `User chose ${start}–${end} seconds`, framing: "Manual crop and zoom", typography: "User-selected cue caption style", subtitle_treatment: cues.length ? "Uploaded exact cue timing, no invented word alignment" : "No uploaded captions", visual_effects: "No added effects", audio_treatment: "Original audio with local normalization", ending_structure: "User-selected endpoint" } };
  if (plan.manual_metadata.description.length > 2000 || plan.hook.length > 140) throw new Error("Shorten the description or opening hook.");
  return validatePlan(plan, source.media_info.duration);
}

export function manualMetadata(plan: BrowserRow, rules: BrowserRow): BrowserRow {
  const supplied = plan.manual_metadata || {}; let text = supplied.description || plan.transcript_excerpt || "";
  for (const required of [...rules.required_mentions, ...rules.required_disclosures]) if (!containsRequiredToken(text, required)) text = (text + "\n\n" + required).trim();
  const variant = { title: supplied.title || plan.title, description: text, caption: text, hashtags: [...new Set([...(supplied.hashtags || []), ...rules.required_hashtags])], keywords: [], opening_hook: plan.hook || "", call_to_action: "", score: 0, reasoning: "User-written metadata formatted locally. Not AI generated, optimized, or scored." };
  const metadata = Object.fromEntries(PLATFORMS.map(platform => [platform, { recommended_index: 0, variants: [structuredClone(variant), structuredClone(variant), structuredClone(variant)] }]));
  return validateMetadata(metadata);
}

export function validateMetadata(metadata: BrowserRow): BrowserRow {
  for (const platform of PLATFORMS) {
    const data = metadata[platform];
    if (!data || !Array.isArray(data.variants) || data.variants.length !== 3 || !Number.isInteger(data.recommended_index) || data.recommended_index < 0 || data.recommended_index > 2) throw new Error("Supply three metadata slots per platform and a valid selected index.");
    for (const variant of data.variants) {
      if (typeof variant.title !== "string" || !variant.title.trim() || variant.title.length > 100 || typeof variant.description !== "string" || variant.description.length > 5000 || typeof variant.caption !== "string" || variant.caption.length > 2200 || !Array.isArray(variant.hashtags) || variant.hashtags.length > 30 || variant.hashtags.some((tag: unknown) => typeof tag !== "string")) throw new Error("Metadata is incomplete or exceeds platform text limits.");
    }
  }
  return metadata;
}

export function compliance(plan: BrowserRow, metadata: BrowserRow, rules: BrowserRow, media: BrowserRow, rights: boolean, semanticEvidence: BrowserRow = {}, draftApproved = false): BrowserRow {
  const checks: BrowserRow[] = [];
  function add(rule: string, state: string, detail: string) { checks.push({ rule, status: state, detail, blocking: state !== "PASS" }); }
  function review(rule: string, detail: string) { const evidence = semanticEvidence[rule]; if (evidence?.confirmed && typeof evidence.note === "string" && evidence.note.trim().length >= 8 && evidence.reviewed_at) add(rule, "PASS", "Human-reviewed evidence: " + evidence.note); else add(rule, "REVIEW_REQUIRED", detail); }
  add("source_rights", rights ? "PASS" : "FAIL", "User rights attestation; not independent rights verification.");
  const duration = media.duration;
  if (!Number.isFinite(duration) || duration <= 0) add('duration', 'REVIEW_REQUIRED', 'A valid measured output duration is required.');
  else add("duration", rules.min_duration != null && duration < rules.min_duration - .05 || rules.max_duration != null && duration > rules.max_duration + .05 ? "FAIL" : "PASS", `Rendered duration: ${duration.toFixed(2)} seconds. Compare with the reviewed campaign bounds.`);
  add("video_format", media.width === 1080 && media.height === 1920 && media.decode_verified && media.codec === "h264" && media.has_audio ? "PASS" : "FAIL", "Actual local encode, metadata probe, and complete decode must confirm vertical H.264 video with audio.");
  if (plan.subtitles_enabled && plan.transcript_excerpt) add("subtitle_sync", media.subtitle_synchronized ? "PASS" : "FAIL", "Uploaded cue timestamps are mapped through the selected scenes. Word alignment is not inferred.");
  if (rules.allowed_platforms.length) add("platforms", "PASS", "Supplied permitted platforms: " + rules.allowed_platforms.join(", ")); else review("platforms", "The brief does not establish allowed platforms.");
  for (const platform of rules.allowed_platforms.length ? rules.allowed_platforms : PLATFORMS) {
    const selected = metadata[platform].variants[metadata[platform].recommended_index];
    const text = [selected.title, selected.description, selected.caption, ...selected.hashtags].join(" ");
    const missing = [...rules.required_hashtags, ...rules.required_mentions, ...rules.required_disclosures].filter(value => !containsRequiredToken(text, value));
    add(`metadata_${platform}`, missing.length ? "FAIL" : "PASS", missing.length ? "Missing required campaign text: " + missing.join(", ") : "Selected metadata includes the supplied mandatory text.");
  }
  for (const [field, rule] of [["required_branding", "branding"], ["prohibited_content", "content_restrictions"], ["audio_restrictions", "audio_restrictions"], ["permitted_source_material", "source_material"]]) if (rules[field].length) review(rule, "Review the actual video against: " + rules[field].join("; "));
  if (rules.required_disclosures.some((value: string) => /on.?screen|spoken|verbal|audio/i.test(value))) review('disclosures', 'Verify the required disclosure delivery in the actual video. Metadata text alone does not establish on-screen or spoken compliance.');
  if (rules.draft_approval_required === true) add("draft_approval", draftApproved ? "PASS" : "REVIEW_REQUIRED", "Campaign draft approval must be confirmed before publication.");
  else if (rules.draft_approval_required === false) add("draft_approval", "PASS", "The supplied rules explicitly state that pre-approval is not required.");
  else review("approval_requirement", "The campaign does not establish its draft approval requirements.");
  if (rules.uncertainties.length) review("campaign_uncertainties", rules.uncertainties.join("; "));
  if (rules.contradictions.length) review("campaign_contradictions", rules.contradictions.join("; "));
  if (!rules.evidence.length) review("campaign_evidence", "Review the original campaign requirements and retain evidence.");
  if (!rules.prohibited_content.length) review("content_restrictions", "Review context and framing in the actual rendered video; no AI semantic analysis was performed.");
  const state = checks.some(check => check.status === "FAIL") ? "FAIL" : checks.some(check => check.status === "REVIEW_REQUIRED") ? "REVIEW_REQUIRED" : "PASS";
  return { status: state, publish_ready: state === "PASS", checks, rules_snapshot: rules, semantic_evidence: semanticEvidence };
}
