"use client";

/** Same API shape as the Python app, using this browser's own storage and CPU. */
import { strToU8, zipSync } from "fflate";
import { audit, claimQueuedJob, getBlob, getRecord, listRecords, mediaUrl, modifyRecord, putBlob, recordId, setRecord, timestamp, type BrowserRow } from "./browser-db";
import { compliance, extractRules, manualMetadata, manualPlan, parseSubtitles, validateMetadata, validatePlan, validateRules,enforceCampaignMetadata, type CaptionCue } from "./browser-rules";
import { inspectVideo } from "./browser-media";
import {renderClipForBrowser} from './browser-rendering';

const LOCAL_USER = { id: "browser-local-owner", name: "Local", email: "", local_workspace: true };
const SOURCE_LIMIT = 150 * 1024 * 1024;
let initialization: Promise<void> | undefined;
let queueRunning = false;
const runnerId = (() => {
  if (typeof window === "undefined") return "";
  try { const saved = sessionStorage.getItem("acf-browser-tab"); if (saved) return saved; const id = crypto.randomUUID(); sessionStorage.setItem("acf-browser-tab", id); return id; } catch { return crypto.randomUUID(); }
})();

function configuration(): BrowserRow {
  return { free_mode: true, local_no_auth: true, browser_mode: true, processing_provider: "browser_manual", external_calls_enabled: false, ai: false, ffmpeg: true, storage: "browser_indexeddb", youtube: false, ai_model: null, transcription_model: null, max_upload_mb: 150, max_clip_seconds: 180, monthly_spend_limit_usd: 0, max_job_cost_usd: 0, retention_days: null, publishing: { youtube: "manual_package", tiktok: "manual_package", instagram: "manual_package", content_rewards: "manual_submission" }, budget_note: "No paid AI, storage subscription or rendering service is required. This browser supplies processing and site storage. Remotion sends render-usage telemetry; video files stay on your device until you choose to upload them. Keep the tab open while rendering." };
}

async function initialize(): Promise<void> {
  if (!initialization) initialization = (async () => {
    const jobs = await listRecords("jobs");
    for (const job of jobs) if (job.status === "processing" && (job.runner_id === runnerId || job.lease_until < Date.now())) await setRecord("jobs", { ...job, status: "failed", error: "The browser tab closed or rendering was interrupted. The original source is saved locally; retry this job when ready.", stage: "Local render interrupted", lease_until: null });
    void pumpQueue();
  })();
  return initialization;
}

async function required(table: string, id: string): Promise<BrowserRow> {
  const record = await getRecord(table, id);
  if (!record) throw new Error("This record is not available in the current browser workspace.");
  return record;
}

function body(options: RequestInit): BrowserRow {
  if (!options.body) return {};
  if (typeof options.body !== "string") throw new Error("This action expects JSON data.");
  try { return JSON.parse(options.body); } catch { throw new Error("The supplied JSON is invalid."); }
}
function form(options: RequestInit): FormData {
  if (!(options.body instanceof FormData)) throw new Error("This action expects an uploaded file.");
  return options.body;
}
function uploaded(options: RequestInit): { file: File; data: FormData } {
  const data = form(options), file = data.get("file");
  if (!(file instanceof File) || !file.size) throw new Error("Choose a nonempty file.");
  return { file, data };
}
function validateUrl(value: unknown, platform?: string): string {
  let url: URL;
  try { url = new URL(String(value)); } catch { throw new Error("Provide a valid HTTPS URL."); }
  if (url.protocol !== "https:" || url.username || url.password) throw new Error("Use an HTTPS URL without embedded credentials.");
  if (platform) {
    const domains: BrowserRow = { youtube: ["www.youtube.com", "youtube.com", "youtu.be"], tiktok: ["www.tiktok.com", "tiktok.com"], instagram: ["www.instagram.com", "instagram.com"] };
    if (!domains[platform]?.includes(url.hostname) || !url.pathname.replace(/\//g, "")) throw new Error("Use a published post URL on the selected official platform.");
  }
  return url.href;
}

function documentRules(brief:string,name:string,attachments:BrowserRow[]){
  const rules=extractRules([brief,...attachments.map(a=>a.extracted_text||'')].join('\n'),name);
  rules.evidence=rules.evidence.map((e:BrowserRow)=>({...e,source:brief.includes(e.quote)?'brief':attachments.find(a=>a.extracted_text?.includes(e.quote))?.filename||'combined documents'}));
  return rules;
}

async function clipJson(clip: BrowserRow): Promise<BrowserRow> {
  const url = await mediaUrl(clip.storage_key);
  return { ...clip, preview_url: url, download_url: url, package_url: null, metadata: clip.metadata_json, plan: clip.plan };
}

function submissionJson(submission: BrowserRow): BrowserRow {
  const seconds = submission.deadline && submission.status === "pending" ? Math.max(0, Math.floor((new Date(submission.deadline).getTime() - Date.now()) / 1000)) : null;
  const warning = seconds === null ? null : seconds <= 0 ? "expired" : seconds <= 300 ? "5 minutes remaining" : seconds <= 600 ? "10 minutes remaining" : seconds <= 900 ? "15 minutes remaining" : null;
  return { ...submission, seconds_remaining: seconds, warning };
}

async function metrics(): Promise<BrowserRow> {
  const [campaigns, clips, jobs, posts, submissions, earnings, costs, observations] = await Promise.all([listRecords("campaigns"), listRecords("clips"), listRecords("jobs"), listRecords("posts"), listRecords("submissions"), listRecords("earnings"), listRecords("costs"), listRecords("observations")]);
  let views = 0;
  for (const post of posts) { const latest = observations.find(row => row.post_id === post.id); if (latest) views += Number(latest.reported_views || 0); }
  const amount = (kind: string) => earnings.filter(row => row.kind === kind && row.currency === "USD").reduce((sum, row) => sum + row.amount, 0);
  return { active_campaigns: campaigns.filter(row => ["active", "review"].includes(row.status)).length, clips_generated: clips.length, processing_jobs: jobs.filter(row => ["queued", "processing"].includes(row.status)).length, ready_to_publish: clips.filter(row => row.compliance?.status === "PASS").length, scheduled: 0, published: posts.length, pending_submissions: submissions.filter(row => ["pending", "submitted"].includes(row.status)).length, approved_submissions: submissions.filter(row => row.status === "approved").length, rejected_submissions: submissions.filter(row => row.status === "rejected").length, reported_views: views, estimated_earnings: amount("estimated"), confirmed_earnings: amount("confirmed"), paid_earnings: amount("paid"), processing_expenses: costs.reduce((sum, row) => sum + row.amount, 0), currency: "USD", earnings_provenance: "Explicit local imports and manual reports only. No external analytics or payouts inferred." };
}

async function updateJob(id: string, changes: BrowserRow): Promise<BrowserRow> {
  return modifyRecord('jobs', id, job => {
    // Delayed worker progress events must not overwrite a terminal result.
    if (!changes.status && job.status !== 'processing') return job;
    return { ...job, ...changes, lease_until: changes.status === "completed" || changes.status === "failed" ? null : Date.now() + 300000 };
  });
}

// Validate what will actually be encoded, including settings changed in the editor.
async function creativePreflight(plan: BrowserRow, sources: BrowserRow[], rules: BrowserRow) {
  if (!plan.creative_concept) return;
  const { validateConcept } = await import('./creative/index');
  const concept = {
    ...plan.creative_concept, shots: plan.scenes,
    output_width: plan.output_width, output_height: plan.output_height,
    caption_settings: plan.caption_settings,
    audio_treatment: plan.audio_treatment,
    manual_decisions: String(plan.manual_decisions || plan.creative_concept.manual_decisions || ''),
  };
  const result = validateConcept(concept, sources as any, validateRules(rules));
  if (!result.render_allowed) throw new Error(result.checks.filter(check => check.blocking && check.status !== 'PASS').map(check => check.detail).join(' ') || 'Resolve the storyboard requirements before rendering.');
  plan.creative_concept = concept;
  return result;
}

async function renderJob(job: BrowserRow): Promise<void> {
  const started = performance.now();
  try {
    const source = await required("sources", job.source_id), campaign = await required("campaigns", job.campaign_id);
    const captions = await getRecord("subtitles", source.id);
    const cues: CaptionCue[] = captions?.cues || [];
    const available=await listRecords('sources');
    const durations=Object.fromEntries(available.map(item=>[item.id,item.media_info.duration]));
    const plan = job.payload.plan ? validatePlan(job.payload.plan, source.media_info.duration,durations) : manualPlan(job.payload.manual_selection, source, job.rules_snapshot, cues);
    await creativePreflight(plan, available, job.rules_snapshot);
    const sourceFiles: Record<string,{blob:Blob;cues:CaptionCue[]}>={};
    for(const id of new Set<string>([source.id,...plan.scenes.map((scene:BrowserRow)=>scene.source_id||source.id),...plan.scenes.filter((scene:BrowserRow)=>scene.secondary_source_id).map((scene:BrowserRow)=>scene.secondary_source_id)])){
      const item=await required('sources',id);
      sourceFiles[id]={blob:await getBlob(item.storage_key),cues:(await getRecord('subtitles',id))?.cues||[]};
    }
    plan.required_on_video_text=[...(job.rules_snapshot.required_on_video_text||[])];
    const metadata = job.payload.metadata || manualMetadata(plan, job.rules_snapshot);
    for(const block of Object.values(metadata) as BrowserRow[])block.variants=block.variants.map((v:BrowserRow)=>enforceCampaignMetadata(v,job.rules_snapshot));
    const result = await renderClipForBrowser(await getBlob(source.storage_key), {...plan,source_id:source.id}, cues, job.mode, (stage, progress) => updateJob(job.id, { stage, progress }).then(() => undefined),sourceFiles);
    let clip: BrowserRow;
    if (job.payload.clip_id) {
      clip = await required("clips", job.payload.clip_id);
      if (clip.current_version !== job.payload.base_version) throw new Error("This clip changed while its edit was queued. Review and render the new version again.");
      clip = { ...clip, current_version: clip.current_version + 1 };
    } else clip = { id: recordId(), created_at: timestamp(), current_version: 1, versions: [] };
    const storageKey = `clips/${clip.id}/v${clip.current_version}.mp4`;
    await putBlob(storageKey, result.blob);
    if('baseBlob' in result&&result.baseBlob){const key=`clips/${clip.id}/v${clip.current_version}-base.mp4`;await putBlob(key,result.baseBlob);result.media_info.remotion_base_key=key;}
    const checks = compliance(plan, metadata, job.rules_snapshot, result.media_info, source.rights_confirmed);
    clip = { ...clip, job_id: job.id, source_id: source.id, campaign_id: campaign.id, title: plan.title, storage_key: storageKey, media_info: result.media_info, metadata_json: metadata, edit_dna: plan.edit_dna, plan, rules_snapshot: job.rules_snapshot, compliance: checks, status: checks.status === "PASS" ? "ready" : "review", draft_approved: false, generation_method: plan.generation_method || "manual_local", versions: [...clip.versions, { id: recordId(), version: clip.current_version, created_at: timestamp(), plan, metadata_json: metadata, storage_key: storageKey }] };
    await setRecord("clips", clip);
    await audit("clip.rendered", clip.id, { renderer: result.media_info.renderer||'ffmpeg_wasm_single_thread', version: clip.current_version, compliance: checks.status });
    await updateJob(job.id, { status: "completed", stage: "Clip rendered locally; review the actual video and campaign checks", progress: 100, completed_clips: 1, completed_at: timestamp(), first_clip_seconds: (performance.now() - started) / 1000, error: null });
  } catch (failure) {
    await updateJob(job.id, { status: "failed", stage: "Local rendering stopped; source preserved", error: failure instanceof Error ? failure.message : String(failure) });
  }
}

async function pumpQueue(): Promise<void> {
  if (queueRunning) return;
  queueRunning = true;
  try {
    while (true) {
      const queued = (await listRecords("jobs")).filter(job => job.status === "queued").reverse();
      if (!queued.length) break;
      const job = await claimQueuedJob(queued[0].id, runnerId);
      if (job) await renderJob(job);
    }
  } finally { queueRunning = false; }
}

async function queueRender(data: BrowserRow): Promise<BrowserRow> {
  const source = await required("sources", data.source_id), campaign = await required("campaigns", data.campaign_id);
  if (data.clip_count && data.clip_count !== 1) throw new Error("Browser mode renders one manual clip at a time.");
  if (!["fast", "quality"].includes(data.mode || "fast")) throw new Error("Choose FAST or QUALITY encoding.");
  const active = (await listRecords("jobs")).find(job => job.source_id === source.id && ["queued", "processing"].includes(job.status));
  if (active) throw new Error("This source already has a queued or active render. Wait for its result before starting another.");
  const subtitle = await getRecord("subtitles", source.id);
  const available=await listRecords('sources');
  const durations=Object.fromEntries(available.map(item=>[item.id,item.media_info.duration]));
  const plan = data.plan ? validatePlan({...data.plan,source_id:source.id}, source.media_info.duration,durations) : manualPlan(data.manual_selection || {}, source, campaign.rules, subtitle?.cues || []);
  if(plan.creative_concept){
    plan.manual_decisions=String(data.director?.manual_decision_note||plan.manual_decisions||plan.creative_concept.manual_decisions||'');
    await creativePreflight(plan,available,data.rules_snapshot||campaign.rules);
    if(data.director?.project_id)await required('director_projects',data.director.project_id);
  }
  const job = { id: recordId(), created_at: timestamp(), source_id: source.id, campaign_id: campaign.id, campaign_name: campaign.name, director:data.director||null, mode: data.mode || "fast", clip_count: 1, status: "queued", stage: "Waiting for this tab's local renderer", progress: 0, attempts: 0, completed_clips: 0, cost_reservation: 0, rules_snapshot: structuredClone(data.rules_snapshot || campaign.rules), payload: { manual_selection: data.manual_selection, plan, ...(data.payload || {}) } };
  await setRecord("jobs", job);
  await audit("job.queued", job.id, { processing_provider: "browser_manual", cost_reservation: 0 });
  void pumpQueue();
  return job;
}

function number(value: unknown, name: string, maximum = 100000000): number {
  const converted = Number(value); if (!Number.isFinite(converted) || converted < 0 || converted > maximum) throw new Error(`${name} must be a valid nonnegative number.`); return converted;
}

function parseCsv(text: string): BrowserRow[] {
  const rows: string[][] = []; let current = "", line: string[] = [], quoted = false;
  for (let index = 0; index < text.length; index++) {
    const character = text[index];
    if (character === '"') { if (quoted && text[index + 1] === '"') { current += '"'; index++; } else quoted = !quoted; }
    else if (character === "," && !quoted) { line.push(current); current = ""; }
    else if (character === "\n" && !quoted) { line.push(current.replace(/\r$/, "")); rows.push(line); line = []; current = ""; }
    else current += character;
  }
  if (quoted) throw new Error("CSV contains an unmatched quote.");
  if (current || line.length) { line.push(current.replace(/\r$/, "")); rows.push(line); }
  const headers = rows.shift()?.map(value => value.replace(/^\uFEFF/, "").trim());
  if (!headers?.includes("post_url") || !headers.includes("reported_views")) throw new Error("CSV requires post_url and reported_views columns.");
  if (rows.length > 1000) throw new Error("CSV imports are limited to 1,000 rows.");
  return rows.filter(row => row.some(Boolean)).map(row => Object.fromEntries(headers.map((header, index) => [header, row[index] || ""])));
}

/** Routes intentionally implement local data/actions rather than simulated jobs. */
export async function browserApi(path: string, options: RequestInit = {}): Promise<any> {
  await initialize();
  path = path.replace(/^\/api(?=\/)/, "").split("?")[0];
  const method = (options.method || "GET").toUpperCase(), parts = path.split("/").filter(Boolean);
  if (path === "/health") return { status: "ok", version: "0.2.0-browser", ...configuration() };
  if (path === "/auth/me") return { ...LOCAL_USER, preferences: (await getRecord("settings", "workspace"))?.preferences || {} };
  if (path.startsWith("/auth/")) throw new Error("This browser workspace opens directly. No account or login is required.");
  if (path === "/settings") {
    if (method === "PATCH") { const values = body(options); await setRecord("settings", { id: "workspace", preferences: { ...values, monthly_spend_limit_usd: 0, max_job_cost_usd: 0 } }); }
    return { ...configuration(), preferences: (await getRecord("settings", "workspace"))?.preferences || {} };
  }
  if (path === "/dashboard") return { metrics: await metrics(), campaigns: (await listRecords("campaigns")).slice(0, 5), clips: await Promise.all((await listRecords("clips")).slice(0, 6).map(clipJson)), recent_jobs: (await listRecords("jobs")).slice(0, 5), configuration: configuration() };
  if(parts[0]==='director'&&parts[1]==='projects'){
    if(parts.length===2&&method==='GET')return listRecords('director_projects');
    if((method==='POST'&&parts.length===2)||(method==='PATCH'&&parts.length===3)){
      const values=body(options);
      if(JSON.stringify(values).length>4000000)throw new Error('This storyboard exceeds the local project size limit. Reduce its image samples or shots.');
      const previous=parts[2]?await required('director_projects',parts[2]):null;
      const sourceId=values.source_id||previous?.source_id,campaignId=values.campaign_id||previous?.campaign_id;
      await required('sources',sourceId);await required('campaigns',campaignId);
      const next={...(previous||{}),...values,id:previous?.id||recordId(),source_id:sourceId,campaign_id:campaignId,created_at:previous?.created_at||timestamp(),updated_at:timestamp()};
      await setRecord('director_projects',next);await audit('director.project_saved',next.id,{manual_edits_preserved:true});return next;
    }
    if(parts.length===3&&method==='GET')return required('director_projects',parts[2]);
  }
  if (parts[0] === "campaigns") {
    if (parts.length === 1 && method === "GET") return listRecords("campaigns");
    if (parts.length === 1 && method === "POST") {
      const values = body(options), name = String(values.name || "").trim(), brief = String(values.brief || "");
      if (!name || name.length > 250 || brief.length > 100000) throw new Error("Supply a campaign name and a brief shorter than 100,000 characters.");
      const rules = extractRules(brief, name), record = { id: recordId(), created_at: timestamp(), name, brief, url: values.url ? validateUrl(values.url) : null, status: "review", review_required: true, rules, evidence: rules.evidence, attachments: [], rule_versions: [{ version: 1, rules, created_at: timestamp() }], analysis_error: null, analysis_method: "local_labeled_text" };
      await setRecord("campaigns", record); await audit("campaign.created", record.id); return record;
    }
    const campaign = await required("campaigns", parts[1]);
    if (parts[2] === "analyze" && method === "POST") {
      const attachments=[];
      for(const attachment of campaign.attachments){
        if(!attachment.extracted_text&&/\.(pdf|txt)$/i.test(attachment.filename)){const {readRulesDocument}=await import('./browser-pdf');attachments.push({...attachment,extracted_text:await readRulesDocument(new File([await getBlob(attachment.storage_key)],attachment.filename))});}
        else attachments.push(attachment);
      }
      const rules = documentRules(campaign.brief,campaign.name,attachments); const updated = { ...campaign, attachments,rules, evidence: rules.evidence, review_required: true, status: "review", analysis_error: null, rule_versions: [...campaign.rule_versions, { version: campaign.rule_versions.length + 1, rules, created_at: timestamp() }] };
      await setRecord("campaigns", updated); return updated;
    }
    if (parts[2] === "rules" && method === "PATCH") {
      const values = body(options); if (String(values.note || "").trim().length < 8) throw new Error("Add an evidence note of at least 8 characters.");
      const rules = validateRules(values.rules); const review = rules.uncertainties.length > 0 || rules.contradictions.length > 0;
      const updated = { ...campaign, rules, review_required: review, status: review ? "review" : "active", evidence: [...campaign.evidence, { source: "manual_review", note: values.note, reviewed_at: timestamp(), reviewed_by: LOCAL_USER.id }], rule_versions: [...campaign.rule_versions, { version: campaign.rule_versions.length + 1, rules, created_at: timestamp() }] };
      await setRecord("campaigns", updated); await audit("campaign.rules_reviewed", campaign.id, { note: values.note }); return updated;
    }
    if (parts[2] === "attachments" && method === "POST") {
      const { file } = uploaded(options); if (file.size > 15 * 1024 * 1024 || !/\.(pdf|txt|png|jpe?g)$/i.test(file.name)) throw new Error("Campaign evidence supports PDF, TXT, PNG or JPEG files up to 15 MB.");
      let extracted='';
      if(/\.(pdf|txt)$/i.test(file.name)){const {readRulesDocument}=await import('./browser-pdf');extracted=await readRulesDocument(file);}
      const key = `campaigns/${campaign.id}/${recordId()}`; await putBlob(key, file);
      const attachments=[...campaign.attachments,{filename:file.name,storage_key:key,size_bytes:file.size,extracted_text:extracted}];
      const rules=documentRules(campaign.brief,campaign.name,attachments);
      if(!extracted)rules.uncertainties.push('Read this image and paste any mandatory wording; image OCR is unavailable.');
      const updated = { ...campaign, attachments, review_required: true, status: "review", rules,evidence:rules.evidence };
      await setRecord("campaigns", updated); return updated;
    }
  }
  if (parts[0] === "sources") {
    if (parts.length === 1 && method === "GET") return listRecords("sources");
    if (parts.length === 1 && method === "POST") {
      const { file, data } = uploaded(options);
      if (data.get("rights_confirmed") !== "true" || String(data.get("rights_note") || "").trim().length < 8) throw new Error("Confirm source rights and supply a meaningful ownership or permission note.");
      if (file.size > SOURCE_LIMIT || !/\.(mp4|mov|m4v|webm|mkv)$/i.test(file.name)) throw new Error("Browser mode accepts playable MP4/MOV/WebM/Matroska files up to 150 MB.");
      const mediaInfo = await inspectVideo(file), id = recordId(), key = `sources/${id}`;
      await putBlob(key, file);
      const record = { id, created_at: timestamp(), filename: file.name, storage_key: key, size_bytes: file.size, media_info: mediaInfo, rights_confirmed: true, original_creator:data.get('source_role')==='original_creator', rights_note: String(data.get("rights_note")), rights_recorded_at: timestamp() };
      await setRecord("sources", record); await audit("source.uploaded", id, { rights_note: record.rights_note, size_bytes: file.size }); return record;
    }
    const source = await required("sources", parts[1]);
    if(parts[2]==='asset'&&method==='GET')return {url:await mediaUrl(source.storage_key)};
    if(parts[2]==='subtitles'&&method==='GET'){const saved=await getRecord('subtitles',source.id);return {cues:saved?.cues||[],words:[],provider:saved?.provider||'none'};}
    if (parts[2] === "subtitles" && method === "POST") {
      if ((await listRecords("jobs")).some(job => job.source_id === source.id && ["queued", "processing"].includes(job.status))) throw new Error("Wait for the current source render to finish before replacing subtitles.");
      const { file } = uploaded(options); if (file.size > 2 * 1024 * 1024) throw new Error("Subtitle files are limited to 2 MB.");
      const cues = parseSubtitles(await file.text(), file.name.split(".").pop() || "", source.media_info.duration);
      await setRecord("subtitles", { id: source.id, created_at: timestamp(), cues, filename: file.name, provider: "manual_subtitle_upload", words: [] });
      await audit("source.subtitles_imported", source.id, { cues: cues.length, timing: "supplied_cue_timestamps" });
      return { source_id: source.id, provider: "manual_subtitle_upload", cues: cues.length, timing: "cue", word_timing_available: false };
    }
  }
  if (parts[0] === "jobs") {
    if (parts.length === 1 && method === "GET") return listRecords("jobs");
    if (parts.length === 1 && method === "POST") return queueRender(body(options));
    if (parts[2] === "retry" && method === "POST") { const job = await required("jobs", parts[1]); if (job.status !== "failed" || job.attempts >= 3) throw new Error("Only failed local jobs with fewer than three attempts can resume."); await setRecord("jobs", { ...job, status: "queued", error: null, stage: "Waiting for the local renderer" }); void pumpQueue(); return required("jobs", job.id); }
  }
  if (parts[0] === "clips") {
    if (parts.length === 1 && method === "GET") return Promise.all((await listRecords("clips")).map(clipJson));
    const clip = await required("clips", parts[1]);
    if (parts.length === 2 && method === "GET") return clipJson(clip);
    if(parts[2]==='remotion'&&method==='GET')return clip.media_info.remotion_base_key?{...clip.media_info.remotion_props,videoUrl:await mediaUrl(clip.media_info.remotion_base_key)}:null;
    if (["download", "video", "package"].includes(parts[2])) throw new Error("Use this clip’s download button to save its local browser file.");
    if (parts[2] === "metadata" && method === "PATCH") {
      const raw=body(options).metadata;for(const block of Object.values(raw) as BrowserRow[])block.variants=block.variants.map((v:BrowserRow)=>enforceCampaignMetadata(v,clip.rules_snapshot));
      const metadata = validateMetadata(raw); const source = await required("sources", clip.source_id);
      const next: BrowserRow = { ...clip, metadata_json: metadata, current_version: clip.current_version + 1, draft_approved: false, compliance: compliance(clip.plan, metadata, clip.rules_snapshot, clip.media_info, source.rights_confirmed), versions: [...clip.versions, { id: recordId(), version: clip.current_version + 1, created_at: timestamp(), plan: clip.plan, metadata_json: metadata, storage_key: clip.storage_key }] };
      next.status = next.compliance.status === "PASS" ? "ready" : "review"; await setRecord("clips", next); await audit("clip.metadata_updated", clip.id); return clipJson(next);
    }
    if (parts[2] === "review" && method === "POST") {
      const values = body(options); if (String(values.note || "").trim().length < 8) throw new Error("A meaningful review evidence note is required.");
      const allowed = ["branding", "content_restrictions", "audio_restrictions", "source_material", "campaign_uncertainties", "campaign_contradictions", "platforms", "approval_requirement", "disclosures", "campaign_evidence","creative_context","manual_editing","original_footage","music_restrictions","ai_voice_restrictions","paid_promotion","prohibited_footage","audience_restrictions","on_video_text"];
      const evidence: BrowserRow = {};
      for (const [key, value] of Object.entries(values.evidence || {}) as [string, BrowserRow][]) { if (!allowed.includes(key) || value?.confirmed !== true || String(value?.note || "").trim().length < 8) throw new Error("Each semantic check needs confirmation and at least eight characters of evidence."); evidence[key] = { confirmed: true, note: value.note, reviewed_by: LOCAL_USER.id, reviewed_at: timestamp() }; }
      const source = await required("sources", clip.source_id), result = compliance(clip.plan, clip.metadata_json, clip.rules_snapshot, clip.media_info, source.rights_confirmed, evidence, values.draft_approved === true);
      const next = { ...clip, draft_approved: values.draft_approved === true, compliance: { ...result, review_note: values.note }, status: result.status === "PASS" ? "ready" : "review" };
      await setRecord("clips", next); await audit("clip.reviewed", clip.id, { note: values.note, evidence }); return clipJson(next);
    }
    if (parts[2] === "regenerate" && method === "POST") {
      const values = body(options); if (values.optimize_metadata) throw new Error("AI metadata generation is disabled. Use the manual metadata editor.");
      return queueRender({ campaign_id: clip.campaign_id, source_id: clip.source_id, plan: values.plan || clip.plan, mode: values.mode || "fast", rules_snapshot: clip.rules_snapshot, payload: { clip_id: clip.id, base_version: clip.current_version, metadata: clip.metadata_json } });
    }
    if (parts[2] === "regenerate-metadata" || parts[2] === "publish") throw new Error("This free browser workspace uses manual editing and upload packages. No hosted AI or direct social publishing is connected.");
    if (parts[2] === "record-publication" && method === "POST") {
      const values = body(options), url = validateUrl(values.url, values.platform), published = new Date(values.published_at);
      if (String(values.confirmation || "").trim().length < 8 || !Number.isFinite(published.getTime()) || published.getTime() > Date.now() + 60000) throw new Error("Confirm the actual post and provide its actual publication timestamp.");
      if ((await listRecords("posts")).some(post => post.url === url)) throw new Error("This published URL is already recorded.");
      const campaign = await required("campaigns", clip.campaign_id), post = { id: recordId(), created_at: timestamp(), clip_id: clip.id, campaign_id: campaign.id, platform: values.platform, url, published_at: published.toISOString(), provenance: "manual_confirmation", title: clip.title };
      const windowMinutes = campaign.rules.submission_window_minutes;
      const submission = { id: recordId(), created_at: timestamp(), post_id: post.id, campaign_id: campaign.id, campaign_name: campaign.name, post_url: url, published_at: published.toISOString(), status: "pending", submission_url: campaign.rules.submission_url || campaign.url, submission_instructions: campaign.rules.submission_instructions, deadline: windowMinutes ? new Date(published.getTime() + windowMinutes * 60000).toISOString() : null };
      await setRecord("posts", post); await setRecord("submissions", submission); await audit("post.manually_recorded", post.id, { confirmation: values.confirmation }); return { ...post, submission: submissionJson(submission) };
    }
  }
  if (path === "/accounts" || path === "/publishing") return [];
  if (path.startsWith("/accounts/") || path.startsWith("/publishing/")) throw new Error("No external accounts are needed in browser mode. Download your manual upload package instead.");
  if (path === "/submissions") return (await listRecords("submissions")).map(submissionJson);
  if (parts[0] === "submissions" && parts[2] === "confirm" && method === "POST") {
    const record = await required("submissions", parts[1]), values = body(options);
    if (!["submitted", "approved", "rejected"].includes(values.status) || String(values.confirmation || "").trim().length < 8) throw new Error("Provide a supported submission status and meaningful confirmation evidence.");
    const next: BrowserRow = { ...record, status: values.status, confirmed_at: timestamp(), confirmation: values.confirmation };
    await setRecord("submissions", next); await audit("submission.manually_confirmed", next.id, values); return submissionJson(next);
  }
  if (path === "/analytics") {
    const observations = await listRecords("observations");
    return { metrics: await metrics(), posts: (await listRecords("posts")).map(post => ({ ...post, analytics: observations.find(row => row.post_id === post.id) || null })), earnings: await listRecords("earnings"), processing_costs: await listRecords("costs") };
  }
  if (path === "/earnings" && method === "POST") {
    const values = body(options); await required("campaigns", values.campaign_id);
    if (!["estimated", "confirmed", "paid"].includes(values.kind) || !/^[A-Z]{3}$/.test(values.currency || "USD") || String(values.provenance || "").trim().length < 8) throw new Error("Provide a valid earnings category, currency, and evidence note.");
    const record: BrowserRow = { ...values, id: recordId(), created_at: timestamp(), amount: number(values.amount, "Amount"), currency: values.currency || "USD" };
    await setRecord("earnings", record); await audit("earnings.imported", record.id, { kind: record.kind, provenance: record.provenance }); return record;
  }
  if (path === "/costs" && method === "POST") {
    const values = body(options); if (String(values.provider || "").trim().length < 8) throw new Error("Provide the provider and invoice reference.");
    const record = { id: recordId(), created_at: timestamp(), amount: number(values.amount, "Amount", 100000), provider: values.provider, kind: "reported" };
    await setRecord("costs", record); await audit("cost.imported", record.id); return record;
  }
  if (path === "/analytics/import-csv" && method === "POST") {
    const { file } = uploaded(options); if (file.size > 1024 * 1024) throw new Error("CSV files are limited to 1 MB.");
    const rows = parseCsv(await file.text()), posts = await listRecords("posts"), prepared: BrowserRow[] = [];
    for (const row of rows) {
      const post = posts.find(post => post.url === row.post_url); if (!post) throw new Error("A CSV post URL is not recorded in this workspace: " + row.post_url);
      const reported = number(row.reported_views, "Reported views"), eligible = row.eligible_views ? number(row.eligible_views, "Eligible views") : null;
      if (!Number.isInteger(reported) || eligible != null && (!Number.isInteger(eligible) || eligible > reported)) throw new Error("Views must be whole numbers and eligible views cannot exceed reported views.");
      prepared.push({ id: recordId(), created_at: timestamp(), post_id: post.id, reported_views: reported, eligible_views: eligible, likes: row.likes ? number(row.likes, "Likes") : null, shares: row.shares ? number(row.shares, "Shares") : null, provenance: "User CSV import" });
    }
    for (const row of prepared) await setRecord("observations", row);
    await audit("analytics.csv_imported", "workspace", { rows: prepared.length }); return { imported: prepared.length };
  }
  if (path === "/audit") return listRecords("audit");
  throw new Error("This action is not available in the free browser workspace: " + path);
}

/** Save actual browser files; no backend download endpoint is needed. */
export async function browserDownload(path: string): Promise<void> {
  await initialize();
  const parts = path.replace(/^\/api(?=\/)/, "").split("?")[0].split("/").filter(Boolean);
  if (parts[0] !== "clips") throw new Error("Choose a generated clip to download.");
  const clip = await required("clips", parts[1]);
  if(clip.plan?.creative_concept){
    await creativePreflight(clip.plan,await listRecords('sources'),clip.rules_snapshot);
  }
  let blob: Blob, filename: string;
  if (parts[2] === "package") {
    const video = new Uint8Array(await (await getBlob(clip.storage_key)).arrayBuffer());
    const zip = zipSync({ "clip.mp4": [video, { level: 0 }], "metadata.json": strToU8(JSON.stringify(clip.metadata_json, null, 2)), "compliance.json": strToU8(JSON.stringify(clip.compliance, null, 2)), "README.txt": strToU8("Created locally in your browser. Review the actual video and campaign rules before uploading. Upload manually through an authorized platform account, record its actual public URL and publication time, then complete the campaign submission yourself. This package does not publish or submit content.") });
    blob = new Blob([zip.slice().buffer as ArrayBuffer], { type: "application/zip" }); filename = `upload-package-${clip.id.slice(0, 8)}.zip`;
  } else { blob = await getBlob(clip.storage_key); filename = `clip-${clip.id.slice(0, 8)}.mp4`; }
  const url = URL.createObjectURL(blob), anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; document.body.append(anchor); anchor.click(); anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 60000);
}
