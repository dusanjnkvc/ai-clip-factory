/** Conservative local parsing and human review. These helpers make no AI calls. */
import type { BrowserRow } from "./browser-db";

export const PLATFORMS = ["youtube", "tiktok", "instagram"];
const MAX_CAPTIONS = 10000;
function containsRequiredToken(text: string, value: string): boolean {
  const escaped = value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(^|[^\\p{L}\\p{N}_])${escaped}(?=$|[^\\p{L}\\p{N}_])`, 'iu').test(text);
}

export function emptyRules(): BrowserRow {
  return { campaign_name: "Untitled campaign", campaign_type: "unknown", allowed_platforms: [], min_duration: null, max_duration: null, required_hashtags: [], required_mentions: [], required_on_video_text: [], required_description_phrases: [], required_disclosures: [], required_branding: [], required_links: [], permitted_source_material: [], prohibited_content: [], prohibited_footage: [], audience_restrictions: [], audio_restrictions: [], automated_clipping_allowed:null, ai_generated_allowed:null, music_allowed:null, ai_voice_allowed:null, original_footage_required:null, paid_promotion_allowed:null, minimum_views: null, reward_per_1000: null, flat_fee: null, maximum_payout: null, currency: null, draft_approval_required: null, submission_deadline: null, submission_window_minutes: null, submission_instructions: null, submission_url: null, evidence: [], uncertainties: [], contradictions: [] };
}

export function validateRules(supplied: BrowserRow): BrowserRow {
  if (!supplied || typeof supplied !== "object" || Array.isArray(supplied)) throw new Error("Campaign rules must be an object.");
  const rules = { ...emptyRules(), ...structuredClone(supplied) };
  for (const field of ["allowed_platforms", "required_hashtags", "required_mentions", "required_on_video_text", "required_description_phrases", "required_disclosures", "required_branding", "required_links", "prohibited_footage", "audience_restrictions", "permitted_source_material", "prohibited_content", "audio_restrictions", "uncertainties", "contradictions", "evidence"]) {
    if (!Array.isArray(rules[field])) throw new Error(`${field} must be a list.`);
    if (field !== "evidence" && rules[field].some((value: unknown) => typeof value !== "string")) throw new Error(`${field} must contain text values.`);
  }
  if (rules.allowed_platforms.some((platform: string) => !PLATFORMS.includes(platform))) throw new Error("Use youtube, tiktok, or instagram as permitted platforms.");
  if(rules.required_on_video_text.length>6||rules.required_on_video_text.join(' ').length>350)throw new Error('Mandatory on-screen wording exceeds the readable video overlay limit. Review its placement before generating.');
  for (const field of ["min_duration", "max_duration", "minimum_views", "reward_per_1000", "flat_fee", "maximum_payout", "submission_window_minutes"]) {
    if (rules[field] !== null && (!Number.isFinite(rules[field]) || rules[field] < 0)) throw new Error(`${field} must be a nonnegative number or null.`);
  }
  if (rules.draft_approval_required !== null && typeof rules.draft_approval_required !== "boolean") throw new Error("Draft approval must be true, false, or unknown.");
  for(const field of ['automated_clipping_allowed','ai_generated_allowed','music_allowed','ai_voice_allowed','original_footage_required','paid_promotion_allowed']) if(rules[field]!==null&&typeof rules[field]!=='boolean')throw new Error(`${field} must be true, false, or unknown.`);
  for(const value of rules.required_links){try{const url=new URL(value);if(url.protocol!=='https:'||url.username||url.password)throw new Error();}catch{throw new Error('Required links must be HTTPS URLs without embedded credentials.');}}
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
    match=line.match(/^(?:required\s+)?(?:mentions?|accounts?|tags?)\s*:\s*(.+)$/i);
    if(match){const mentions=match[1].match(/@[\p{L}\p{N}_.-]+/gu);if(mentions?.length)assign('required_mentions',[...new Set(mentions)],line);}
    match=line.match(/^(?:required\s+)?(?:on[- ](?:screen|video)\s+(?:text|wording)|text\s+(?:in|on)\s+(?:the\s+)?video)\s*:\s*(.+)$/i);
    if(match)assign('required_on_video_text',[match[1].trim().replace(/^["“]|["”]$/g,'')],line);
    match=line.match(/^required\s+(?:description|caption)(?:\s+(?:text|phrase))?\s*:\s*(.+)$/i);
    if(match)assign('required_description_phrases',[match[1].trim()],line);
    if(/\b(?:must|required|mandatory|include|add|use)\b/i.test(line)&&!/\b(?:do not|don't|optional|prohibited|exclude)\b/i.test(line)&&!/^.*?:/.test(line)){
      const tags=line.match(/#[\p{L}\p{N}_]+/gu),mentions=line.match(/@[\p{L}\p{N}_.-]+/gu);
      if(tags)assign('required_hashtags',[...new Set([...rules.required_hashtags,...tags])],line);
      if(mentions)assign('required_mentions',[...new Set([...rules.required_mentions,...mentions])],line);
    }
    if(/\b(?:must|required|include|write|display)\b/i.test(line)&&/on[- ]screen|on[- ]video|in (?:the )?video/i.test(line)){
      const quoted=line.match(/["“]([^"”]+)["”]/);if(quoted)assign('required_on_video_text',[...new Set([...rules.required_on_video_text,quoted[1]])],line);
    }
    match = line.match(/^(?:clip\s+)?duration\s*:\s*(\d+(?:\.\d+)?)\s*[-–—]\s*(\d+(?:\.\d+)?)\s*(?:s|seconds?)\.?$/i);
    if (match) { assign("min_duration", Number(match[1]), line); assign("max_duration", Number(match[2]), line); }
    match = line.match(/^draft\s+(?:pre[- ]?)?approval\s*:\s*(required|not required|yes|no)\.?$/i);
    if (match) assign("draft_approval_required", ["yes", "required"].includes(match[1].toLowerCase()), line);
    match = line.match(/^submission\s+window\s*:\s*(\d+)\s*(?:m|min|minutes?)\.?$/i);
    if (match) assign("submission_window_minutes", Number(match[1]), line);
    for(const [label,field] of [['Automated clipping','automated_clipping_allowed'],['AI generated videos','ai_generated_allowed'],['Music','music_allowed'],['AI voice','ai_voice_allowed'],['Paid promotion','paid_promotion_allowed']]){
      const explicit=line.match(new RegExp(`^${label}\\s*:\\s*(allowed|permitted|yes|prohibited|not allowed|no)\\.?$`,'i'));
      if(explicit)assign(field,['allowed','permitted','yes'].includes(explicit[1].toLowerCase()),line);
    }
    match=line.match(/^original (?:creator )?footage\s*:\s*(required|yes|not required|no)\.?$/i);if(match)assign('original_footage_required',['required','yes'].includes(match[1].toLowerCase()),line);
    match=line.match(/^required links?\s*:\s*(.+)$/i);if(match)assign('required_links',match[1].trim().split(/\s+/),line);
    if(/^(?:no automated clipping|automated clipping (?:is )?(?:prohibited|not allowed))[.!]?$/i.test(line))assign('automated_clipping_allowed',false,line);
    if(/^(?:no (?:fully )?AI[- ]generated videos|(?:fully )?AI[- ]generated videos (?:are )?(?:prohibited|not allowed))[.!]?$/i.test(line))assign('ai_generated_allowed',false,line);
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

export function validatePlan(plan: BrowserRow, sourceDuration: number, sourceDurations?: Record<string,number>): BrowserRow {
  if (!Number.isFinite(plan.start) || !Number.isFinite(plan.end) || plan.start < 0 || plan.end <= plan.start || plan.end > sourceDuration + .001) throw new Error("Choose start and end times inside your source video.");
  if (!Array.isArray(plan.scenes) || !plan.scenes.length || plan.scenes.length > 20) throw new Error("An editing plan must have 1–20 source scenes.");
  let duration = 0;
  for (const scene of plan.scenes) {
    const isPrimary=!scene.source_id||scene.source_id===plan.source_id;
    const bound=sourceDurations&&scene.source_id?sourceDurations[scene.source_id]:sourceDuration;
    if (![scene.start, scene.end, scene.crop_x, scene.crop_y, scene.zoom,bound].every(Number.isFinite) || scene.start<0 || scene.end>bound+.001 || scene.end<=scene.start || isPrimary&&(scene.start<plan.start||scene.end>plan.end)) throw new Error("A scene is outside its authorized source range.");
    if (scene.crop_x < 0 || scene.crop_x > 1 || scene.crop_y < 0 || scene.crop_y > 1 || scene.zoom < 1 || scene.zoom > 1.5) throw new Error("Use crop coordinates between 0 and 1 and zoom between 1 and 1.5.");
    if(!['fill','fit_blur','split'].includes(scene.composition||'fill')||!['cut','fade'].includes(scene.transition||'cut')||!['none','contrast','retro'].includes(scene.effect||'none'))throw new Error('Choose a supported composition, transition, and effect.');
    for(const field of ['crop_x_end','crop_y_end'])if(scene[field]!=null&&(!Number.isFinite(scene[field])||scene[field]<0||scene[field]>1))throw new Error('Animated crop endpoints must be between 0 and 1.');
    if(scene.overlay_text!=null&&(typeof scene.overlay_text!=='string'||scene.overlay_text.length>180))throw new Error('On-screen labels are limited to 180 characters.');
    if(scene.composition==='split'){
      const second=sourceDurations?.[scene.secondary_source_id],start=scene.secondary_start??0;
      if(!scene.secondary_source_id||!Number.isFinite(second)||!Number.isFinite(start)||start<0||start+scene.end-scene.start>second!+.001)throw new Error('Split screen needs an available second source covering the shot duration.');
    }
    duration += scene.end - scene.start;
  }
  if (duration < 1 || duration > 180) throw new Error("Browser clips must be between 1 and 180 seconds. Use a shorter range to limit browser memory use.");
  if (typeof plan.title !== "string" || !plan.title.trim() || plan.title.length > 100) throw new Error("A clip title of 1–100 characters is required.");
  if(plan.output_width!=null||plan.output_height!=null)if(![[1080,1920],[720,1280],[540,960]].some(([w,h])=>plan.output_width===w&&plan.output_height===h))throw new Error('Choose a supported vertical export resolution.');
  if(plan.audio_treatment!=null&&!['source','mute'].includes(plan.audio_treatment))throw new Error('Audio treatment must preserve or mute source audio.');
  const captions=plan.caption_settings;
  if(captions){
    if(!Number.isFinite(captions.font_size)||captions.font_size<36||captions.font_size>100||!Number.isFinite(captions.safe_top)||captions.safe_top<90||captions.safe_top>600||!Number.isFinite(captions.safe_bottom)||captions.safe_bottom<150||captions.safe_bottom>650)throw new Error('Caption size and safe zones are outside supported bounds.');
    if(!/^#[0-9a-f]{6}$/i.test(captions.color)||!/^#[0-9a-f]{6}$/i.test(captions.highlight)||!['none','fade','pop','slide'].includes(captions.animation)||!['upper','lower','center'].includes(captions.position))throw new Error('Caption colors, animation, or position are invalid.');
  }
  return plan;
}

export function manualPlan(selection: BrowserRow, source: BrowserRow, rules: BrowserRow, cues: CaptionCue[]): BrowserRow {
  const start = Number(selection.start || 0), end = selection.end == null ? Math.min(source.media_info.duration, start + 30) : Number(selection.end);
  const title = String(selection.title || `${source.filename.replace(/\.[^.]+$/, "")} clip`).trim();
  const tags = selection.hashtags || [];
  if (!Array.isArray(tags) || tags.length > 30 || tags.some(tag => typeof tag !== "string" || !/^#[\p{L}\p{N}_]+$/u.test(tag))) throw new Error("Use up to 30 hashtags containing letters, numbers, or underscores.");
  const scene = { start, end, crop_x: Number(selection.crop_x ?? .5), crop_y: Number(selection.crop_y ?? .5), zoom: Number(selection.zoom ?? 1), rationale: "User-selected source range and framing." };
  const plan: BrowserRow = { title, start, end, scenes: [scene], hook: String(selection.hook || ""), show_hook: selection.show_hook === true, subtitle_style: selection.subtitle_style || "clean", subtitles_enabled: cues.length > 0, transcript_excerpt: cues.filter(cue => cue.end > start && cue.start < end).map(cue => cue.text).join(" "), content_type: "general", rationale: "Manual source selection; no AI analysis or ranking was performed.", generation_method: "manual_local", render_engine:selection.render_engine||"remotion", score_origin: "not_scored", semantic_notes: ["Review the actual video, context, framing, campaign rules, and permissions."], scores: { hook_strength: 0, engagement_potential: 0, clarity: 0, standalone_context: 0, campaign_relevance: 0 }, manual_metadata: { title, description: String(selection.description || ""), hashtags: [...new Set(tags)] }, edit_dna: { hook_structure: "User-selected opening", scene_order: "Original source order", cut_timing: `User chose ${start}–${end} seconds`, framing: "Manual crop and zoom", typography: "User-selected cue caption style", subtitle_treatment: cues.length ? "Uploaded exact cue timing, no invented word alignment" : "No uploaded captions", visual_effects: "No added effects", audio_treatment: "Original audio with local normalization", ending_structure: "User-selected endpoint" } };
  if (plan.manual_metadata.description.length > 2000 || plan.hook.length > 140) throw new Error("Shorten the description or opening hook.");
  plan.required_on_video_text=[...(rules.required_on_video_text||[])];
  return validatePlan(plan, source.media_info.duration);
}

export function enforceCampaignMetadata(variant:BrowserRow,rules:BrowserRow):BrowserRow {
  const result=structuredClone(variant),tags:string[]=[],seen=new Set<string>();
  for(const tag of [...(rules.required_hashtags||[]),...(variant.hashtags||[]),...[variant.description||'',variant.caption||''].flatMap(t=>t.match(/#[\p{L}\p{N}_]+/gu)||[])])if(!seen.has(tag.toLocaleLowerCase())){tags.push(tag);seen.add(tag.toLocaleLowerCase());}
  result.hashtags=tags;
  const prefix=[...(rules.required_hashtags||[]),...(rules.required_mentions||[])].join(' ');
  for(const field of ['description','caption']){
    let text=String(variant[field]||'');
    for(const tag of rules.required_hashtags||[]){const escaped=tag.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');text=text.replace(new RegExp('(^|[^\\p{L}\\p{N}_])'+escaped+'(?![\\p{L}\\p{N}_])','giu'),'$1').trim();}
    for(const mention of rules.required_mentions||[]){const escaped=mention.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');text=text.replace(new RegExp('(^|[^\\p{L}\\p{N}_])'+escaped+'(?![\\p{L}\\p{N}_.-])','giu'),'$1').trim();}
    text=[prefix,text].filter(Boolean).join('\n\n');
    for(const phrase of [...(rules.required_disclosures||[]),...(rules.required_links||[]),...(rules.required_description_phrases||[])])if(!text.includes(phrase))text=[text,phrase].filter(Boolean).join('\n\n');
    result[field]=text;
  }
  return result;
}

export function manualMetadata(plan: BrowserRow, rules: BrowserRow): BrowserRow {
  const supplied = plan.manual_metadata || {};
  const variant = enforceCampaignMetadata({title:supplied.title||plan.title,description:supplied.description||plan.transcript_excerpt||'',caption:supplied.description||plan.transcript_excerpt||'',hashtags:supplied.hashtags||[],keywords:[],opening_hook:plan.hook||'',call_to_action:'',score:0,reasoning:'User-written metadata formatted with required campaign text first; not AI generated or scored.'},rules);
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
  rules=validateRules(rules);
  const checks: BrowserRow[] = [];
  function add(rule: string, state: string, detail: string) { checks.push({ rule, status: state, detail, blocking: state !== "PASS" }); }
  function review(rule: string, detail: string) { const evidence = semanticEvidence[rule]; if (evidence?.confirmed && typeof evidence.note === "string" && evidence.note.trim().length >= 8 && evidence.reviewed_at) add(rule, "PASS", "Human-reviewed evidence: " + evidence.note); else add(rule, "REVIEW_REQUIRED", detail); }
  add("source_rights", rights ? "PASS" : "FAIL", "User rights attestation; not independent rights verification.");
  const duration = media.duration;
  if (!Number.isFinite(duration) || duration <= 0) add('duration', 'REVIEW_REQUIRED', 'A valid measured output duration is required.');
  else add("duration", rules.min_duration != null && duration < rules.min_duration - .05 || rules.max_duration != null && duration > rules.max_duration + .05 ? "FAIL" : "PASS", `Rendered duration: ${duration.toFixed(2)} seconds. Compare with the reviewed campaign bounds.`);
  add("video_format", media.width === (plan.output_width||1080) && media.height === (plan.output_height||1920) && media.decode_verified && media.codec === "h264" && media.has_audio ? "PASS" : "FAIL", "Actual local encode, metadata probe, and complete decode must confirm the selected vertical H.264 output with audio.");
  if (plan.subtitles_enabled && plan.transcript_excerpt) add("subtitle_sync", media.subtitle_synchronized ? "PASS" : "FAIL", "Uploaded cue timestamps are mapped through the selected scenes. Word alignment is not inferred.");
  if (rules.allowed_platforms.length) add("platforms", "PASS", "Supplied permitted platforms: " + rules.allowed_platforms.join(", ")); else review("platforms", "The brief does not establish allowed platforms.");
  for (const platform of rules.allowed_platforms.length ? rules.allowed_platforms : PLATFORMS) {
    const selected = metadata[platform].variants[metadata[platform].recommended_index];
    const text = [selected.title, selected.description, selected.caption, ...selected.hashtags].join(" ");
    const missing = [...rules.required_hashtags, ...rules.required_mentions, ...rules.required_disclosures,...rules.required_links,...(rules.required_description_phrases||[])].filter(value => !containsRequiredToken(text, value));
    add(`metadata_${platform}`, missing.length ? "FAIL" : "PASS", missing.length ? "Missing required campaign text: " + missing.join(", ") : "Selected metadata includes the supplied mandatory text.");
  }
  if(rules.required_on_video_text.length){const missing=rules.required_on_video_text.filter((t:string)=>!plan.required_on_video_text?.includes(t));if(missing.length)add('on_video_text','FAIL','Required visible wording is missing from the render plan: '+missing.join('; '));else review('on_video_text','Review exact required text and readability in the actual video: '+rules.required_on_video_text.join('; '));}
  for (const [field, rule] of [["required_branding", "branding"], ["prohibited_content", "content_restrictions"], ["audio_restrictions", "audio_restrictions"], ["permitted_source_material", "source_material"]]) if (rules[field].length) review(rule, "Review the actual video against: " + rules[field].join("; "));
  if (rules.required_disclosures.some((value: string) => /on.?screen|spoken|verbal|audio/i.test(value))) review('disclosures', 'Verify the required disclosure delivery in the actual video. Metadata text alone does not establish on-screen or spoken compliance.');
  if (rules.draft_approval_required === true) add("draft_approval", draftApproved ? "PASS" : "REVIEW_REQUIRED", "Campaign draft approval must be confirmed before publication.");
  else if (rules.draft_approval_required === false) add("draft_approval", "PASS", "The supplied rules explicitly state that pre-approval is not required.");
  else review("approval_requirement", "The campaign does not establish its draft approval requirements.");
  if (rules.uncertainties.length) review("campaign_uncertainties", rules.uncertainties.join("; "));
  if (rules.contradictions.length) review("campaign_contradictions", rules.contradictions.join("; "));
  if (!rules.evidence.length) review("campaign_evidence", "Review the original campaign requirements and retain evidence.");
  if (!rules.prohibited_content.length) review("content_restrictions", "Review context and framing in the actual rendered video; no AI semantic analysis was performed.");
  if(plan.generation_method==='local_assisted')review('creative_context','Confirm that edited shot order, overlays, and publishing suggestions accurately represent the actual footage. Local measurements do not establish meaning.');
  if(rules.automated_clipping_allowed===false||rules.ai_generated_allowed===false)review('manual_editing','The campaign restricts automation. Verify the required human creative decisions and campaign-specific conditions; an app-generated storyboard does not establish eligibility.');
  if(rules.original_footage_required===true)review('original_footage','Verify the required original creator footage and ownership evidence in the actual final video.');
  if(rules.music_allowed===false&&plan.audio_treatment!=='mute')review('music_restrictions','Verify that retained source audio does not include prohibited music.');
  if(rules.ai_voice_allowed===false)review('ai_voice_restrictions','No AI voice is added by this editor. Verify that the original source audio also satisfies the campaign restriction.');
  if(rules.paid_promotion_allowed===false)review('paid_promotion','Verify the proposed use, promotion, and disclosures against the original campaign terms.');
  if(rules.prohibited_footage.length)review('prohibited_footage',rules.prohibited_footage.join('; '));
  if(rules.audience_restrictions.length)review('audience_restrictions',rules.audience_restrictions.join('; '));
  const state = checks.some(check => check.status === "FAIL") ? "FAIL" : checks.some(check => check.status === "REVIEW_REQUIRED") ? "REVIEW_REQUIRED" : "PASS";
  return { status: state, publish_ready: state === "PASS", checks, rules_snapshot: rules, semantic_evidence: semanticEvidence };
}
