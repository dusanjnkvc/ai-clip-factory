"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { ArrowDown, ArrowDownToLine, ArrowRight, ArrowUp, Check, ChevronDown, Clapperboard, Copy, ExternalLink, FileCheck2, Film, Focus, Gauge, Image as ImageIcon, Layers3, LoaderCircle, LockKeyhole, Play, Plus, RefreshCw, Save, Scissors, ShieldCheck, Sparkles, Trash2, Undo2, Redo2, UploadCloud, Video, WandSparkles } from "lucide-react";
import { api } from "@/lib/api";
import { analyzeVideo, analysisFingerprint } from "@/lib/creative/analyzer";
import { STYLES, generateConcepts, toEditPlan, validateConcept, publishingSuggestions, evaluateHook } from "@/lib/creative";
import type { CaptionSettings, ConceptBatch, CreativeConcept, CreativeOptions, Platform, Row, Shot, SourceAnalysis, SourceDescriptor, StyleId } from "@/lib/creative/types";

type Props = { notify: (message: string) => void; onRendered: () => void };
const rows = (value: any): Row[] => Array.isArray(value) ? value : value?.items || [];
const clone = <T,>(value: T): T => structuredClone(value);
const time = (seconds: number) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}.${Math.floor((seconds % 1) * 10)}`;
const date = (value: string) => value ? new Date(value).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "";
const kindLabel = (kind: string) => ({ "high-engagement": "High engagement", cinematic: "Cinematic", "creative-storytelling": "Creative storytelling" }[kind] || kind);
const duration = (concept: CreativeConcept) => concept.shots.reduce((sum, shot) => sum + shot.end - shot.start, 0);
// Serialize project writes across mounts so an older autosave cannot win a later navigation flush.
const projectWrites = new Map<string, Promise<Row>>();
function writeProject(id: string, changes: Row): Promise<Row> {
  const prior = projectWrites.get(id);
  const pending = (prior || Promise.resolve()).catch(() => undefined).then(() => api(`/director/projects/${id}`, { method: "PATCH", body: JSON.stringify(changes) }));
  projectWrites.set(id, pending);
  const release = () => { if (projectWrites.get(id) === pending) projectWrites.delete(id); };
  void pending.then(release, release);
  return pending;
}
function draftChanges(concept: CreativeConcept, batch: ConceptBatch | null, manualNote: string, options: CreativeOptions, originalIds: string[]): Row {
  const savedConcept = { ...clone(concept), manual_decisions: manualNote };
  const concepts = (batch?.concepts || []).map(item => item.id === savedConcept.id ? savedConcept : item);
  return { concepts, batch: batch ? { ...batch, concepts } : null, draft: savedConcept, selected_concept_id: savedConcept.id, manual_decision_note: manualNote, options: clone(options), original_source_ids: [...originalIds] };
}
function Status({ value }: { value: string }) { return <span className={`cd-status ${value.toLowerCase()}`}><span/>{value.replaceAll("_", " ")}</span>; }

export default function CreativeDirector({ notify, onRendered }: Props) {
  const [sources, setSources] = useState<SourceDescriptor[]>([]);
  const [campaigns, setCampaigns] = useState<Row[]>([]);
  const [projects, setProjects] = useState<Row[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [campaignId, setCampaignId] = useState("");
  const [projectId, setProjectId] = useState("");
  const [options, setOptions] = useState<CreativeOptions>({ duration: 30, pace: "balanced", style: "auto", platform: "youtube", mode: "assisted", audience: "", title: "", description: "", audio: "source", output_height: 1920 });
  const [originalIds, setOriginalIds] = useState<string[]>([]);
  const [analysis, setAnalysis] = useState<SourceAnalysis | null>(null);
  const [batch, setBatch] = useState<ConceptBatch | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [draft, setDraft] = useState<CreativeConcept | null>(null);
  const [undo, setUndo] = useState<CreativeConcept[]>([]);
  const [redo, setRedo] = useState<CreativeConcept[]>([]);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [stage, setStage] = useState("");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [previewUrl, setPreviewUrl] = useState("");
  const [previewShotId, setPreviewShotId] = useState("");
  const [previewTime, setPreviewTime] = useState(0);
  const [manualNote, setManualNote] = useState("");
  const [exportMode, setExportMode] = useState("fast");
  const [renderJob, setRenderJob] = useState<Row | null>(null);
  const [replaceRequested, setReplaceRequested] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadRights, setUploadRights] = useState(false);
  const [uploadNote, setUploadNote] = useState("");
  const [platform, setPlatform] = useState<Platform>("youtube");
  const [publishingIndex, setPublishingIndex] = useState(0);
  const sourceVideo = useRef<HTMLVideoElement>(null);
  const abort = useRef<AbortController | null>(null);
  const assetUrls = useRef(new Map<string, string>());
  const editRevision = useRef(0);
  const mounted = useRef(false);
  const latestDraft = useRef<{ id: string; changes: Row } | null>(null);

  const source = sources.find(item => item.id === sourceId);
  const campaign = campaigns.find(item => item.id === campaignId);
  const rules = campaign?.rules || {};
  const selected = batch?.concepts.find(item => item.id === selectedId) || null;
  const concept = draft || selected;
  const originalSources = sources.filter(item => originalIds.includes(item.id));
  const availableSources = sources;

  useEffect(() => {
    latestDraft.current = dirty && projectId && concept ? { id: projectId, changes: draftChanges(concept, batch, manualNote, options, originalIds) } : null;
  }, [dirty, projectId, concept, batch, manualNote, options, originalIds]);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      const pending = latestDraft.current;
      if (pending) void writeProject(pending.id, pending.changes).catch(failure => notify(`Storyboard could not be saved: ${(failure as Error).message}`));
    };
  }, [notify]);

  const loadWorkspace = useCallback(async () => {
    setLoading(true);
    await Promise.allSettled([...projectWrites.values()]);
    const result = await Promise.allSettled([api("/sources"), api("/campaigns"), api("/director/projects")]);
    if (result[0].status === "fulfilled") { const videos = rows(result[0].value) as SourceDescriptor[]; setSources(videos); setSourceId(current => current || videos[0]?.id || ""); }
    if (result[1].status === "fulfilled") { const briefs = rows(result[1].value); setCampaigns(briefs); setCampaignId(current => current || briefs[0]?.id || ""); }
    if (result[2].status === "fulfilled") setProjects(rows(result[2].value));
    const failure = result.find(item => item.status === "rejected");
    if (failure?.status === "rejected") setError(failure.reason instanceof Error ? failure.reason.message : "The workspace could not be loaded.");
    setLoading(false);
  }, []);
  useEffect(() => { void loadWorkspace(); return () => abort.current?.abort(); }, [loadWorkspace]);

  async function asset(id: string): Promise<string> {
    const cached = assetUrls.current.get(id);
    if (cached) return cached;
    const result = await api(`/sources/${id}/asset`);
    if (!result?.url) throw new Error("This source is no longer available. Import the authorized video again.");
    assetUrls.current.set(id, result.url);
    return result.url;
  }
  useEffect(() => {
    let active = true;
    setSourceUrl(""); setPreviewUrl(""); setPreviewShotId(""); if (!sourceId) return;
    asset(sourceId).then(url => { if (active) { setSourceUrl(url); setPreviewUrl(url); setPreviewTime(0); } }).catch(failure => { if (active) setError((failure as Error).message); });
    return () => { active = false; };
  }, [sourceId]);
  useEffect(() => {
    if (!renderJob || !["queued", "processing"].includes(renderJob.status)) return;
    const timer = setInterval(async () => {
      try { const next = rows(await api("/jobs")).find(job => job.id === renderJob.id); if (next) setRenderJob(next); }
      catch { /* A subsequent poll can recover an interrupted UI refresh. */ }
    }, 2000);
    return () => clearInterval(timer);
  }, [renderJob?.id, renderJob?.status]);

  const preflight = useMemo(() => {
    if (!concept) return null;
    try { return validateConcept({ ...concept, manual_decisions: manualNote }, availableSources, rules); }
    catch (failure) { return { status: "FAIL", render_allowed: false, publish_ready: false, assisted_manual_required: true, missing_footage: [], checks: [{ rule: "editing_plan", status: "FAIL", detail: (failure as Error).message, classification: "mandatory", blocking: true }] }; }
  }, [concept, manualNote, availableSources, rules]);
  const suggestions = useMemo(() => {
    if (!concept) return null;
    try { return publishingSuggestions(concept, rules, platform); } catch { return null; }
  }, [concept, rules, platform]);

  useEffect(() => {
    if (!dirty || !projectId || !concept || busy || saving || submitting) return;
    const timer = setTimeout(() => { void saveDraft().catch(failure => setError(`Draft could not be saved: ${(failure as Error).message}`)); }, 900);
    return () => clearTimeout(timer);
  }, [dirty, draft, manualNote, options, originalIds, projectId, busy, saving, submitting]);

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  function editConcept(change: Partial<CreativeConcept> | ((current: CreativeConcept) => CreativeConcept)) {
    if (!concept || busy || submitting) return;
    setUndo(current => [...current.slice(-29), clone(concept)]);
    setRedo([]);
    const updated = typeof change === "function" ? change(clone(concept)) : { ...clone(concept), ...change };
    updated.user_modified = true;
    updated.duration = duration(updated);
    if (analysis) updated.hook_assessment = evaluateHook(updated.hook, analysis, updated.shots[0]?.start || 0);
    editRevision.current += 1;
    setDraft(updated); setDirty(true);
  }
  function editShot(id: string, changes: Partial<Shot>) { editConcept(current => ({ ...current, shots: current.shots.map(shot => shot.id === id ? { ...shot, ...changes, manual_modified: true } : shot) })); }
  async function selectConcept(next: CreativeConcept) {
    if (next.id === selectedId || saving || busy || submitting) return;
    try {
      if (dirty) await saveDraft();
      if (!mounted.current) return;
      setSelectedId(next.id); setDraft(null); setUndo([]); setRedo([]); setDirty(false);
      if (projectId) {
        await writeProject(projectId, { selected_concept_id: next.id, draft: null });
        setProjects(current => current.map(project => project.id === projectId ? { ...project, selected_concept_id: next.id, draft: null } : project));
      }
    } catch (failure) { setError((failure as Error).message); }
  }
  async function saveDraft(): Promise<void> {
    if (!projectId || !concept) return;
    const revision = editRevision.current;
    const changes = draftChanges(concept, batch, manualNote, options, originalIds);
    setSaving(true);
    try {
      const saved = await writeProject(projectId, changes);
      if (!mounted.current) return;
      setProjects(current => current.map(project => project.id === projectId ? { ...project, ...changes, ...saved } : project));
      if (changes.batch) setBatch(changes.batch);
      if (revision === editRevision.current) setDirty(false);
    } finally { if (mounted.current) setSaving(false); }
  }
  async function save() { try { await saveDraft(); notify("Storyboard saved. Your manual decisions are preserved."); } catch (failure) { notify((failure as Error).message); } }

  async function generate(confirmed = false) {
    if (busy || saving || submitting) return;
    if (!source || !campaign) { setError("Choose an authorized source and a campaign brief first. Use Create Clips to add them."); return; }
    if (dirty && !confirmed) { setReplaceRequested(true); return; }
    setReplaceRequested(false); setBusy(true); setError(""); setProgress(0);
    abort.current = new AbortController();
    try {
      if (dirty) await saveDraft();
      const captionData = await api(`/sources/${source.id}/subtitles`);
      const cues = captionData?.cues || [];
      const fingerprint = await analysisFingerprint(source, cues);
      let measured = analysis?.source_id === source.id && analysis.fingerprint === fingerprint ? analysis : projects.find(project => project.source_id === source.id && project.analysis?.fingerprint === fingerprint)?.analysis as SourceAnalysis | undefined;
      if (!measured) measured = await analyzeVideo(source, await asset(source.id), cues, (message, value) => { setStage(message); setProgress(value); }, abort.current.signal);
      else { setStage("Reusing measured source analysis"); setProgress(85); }
      if (abort.current.signal.aborted) throw new DOMException("Analysis cancelled", "AbortError");
      setAnalysis(measured);
      const nextOptions: CreativeOptions = { ...options, manual_decisions: manualNote, variation: projects.filter(project => project.source_id === source.id).length };
      const nextBatch = generateConcepts({ source, analysis: measured, rules, options: nextOptions, history: projects.flatMap(project => project.concepts || []), originalSources });
      if (!nextBatch.concepts.length) throw new Error(nextBatch.unavailable_reasons.join(" ") || "The source does not provide enough distinct material. Adjust duration or add a different authorized source.");
      setStage("Saving source-backed concepts"); setProgress(95);
      const id = nextBatch.recommended_id || nextBatch.concepts[0].id;
      const project = await api("/director/projects", { method: "POST", body: JSON.stringify({ source_id: source.id, campaign_id: campaign.id, options: nextOptions, analysis: measured, concepts: nextBatch.concepts, batch: nextBatch, selected_concept_id: id, manual_decision_note: manualNote, original_source_ids: originalIds }) });
      setProjectId(project.id); setProjects(current => [project, ...current.filter(item => item.id !== project.id)]);
      setBatch(nextBatch); setSelectedId(id); setDraft(null); setUndo([]); setRedo([]); setDirty(false); setRenderJob(null); setProgress(100);
      notify(`${nextBatch.concepts.length} local assisted concept${nextBatch.concepts.length === 1 ? "" : "s"} created from measured frames and supplied captions.`);
    } catch (failure) { if ((failure as Error).name !== "AbortError") setError((failure as Error).message); }
    finally { setBusy(false); setStage(""); }
  }
  async function openProject(id: string) {
    if (saving || busy || submitting || id === projectId) return;
    try { if (dirty) await saveDraft(); } catch (failure) { setError((failure as Error).message); return; }
    if (!mounted.current) return;
    if (!id) { clearProject(); return; }
    const project = projects.find(item => item.id === id);
    if (!project) return;
    setProjectId(id); setSourceId(project.source_id); setCampaignId(project.campaign_id); setOptions(project.options || options); setAnalysis(project.analysis || null);
    setBatch(project.batch || { concepts: project.concepts || [], recommended_id: project.selected_concept_id || null, recommendation: "Saved project", limitations: project.analysis?.limitations || [], unavailable_reasons: [], analysis_method: "local_measured", generation_method: "local_assisted", provider_status: "not_configured" });
    setSelectedId(project.selected_concept_id || project.concepts?.[0]?.id || ""); setDraft(project.draft || null); setOriginalIds(project.original_source_ids || []); setManualNote(project.manual_decision_note || ""); setUndo([]); setRedo([]); setDirty(false); setError(""); setRenderJob(null);
    setPlatform(project.options?.platform || "youtube"); setPublishingIndex(0);
  }
  function clearProject() {
    setProjectId(""); setBatch(null); setSelectedId(""); setDraft(null); setAnalysis(null); setUndo([]); setRedo([]); setDirty(false); setRenderJob(null); setPreviewShotId(""); setReplaceRequested(false); setManualNote("");
  }
  async function changeInput(kind: "source" | "campaign", id: string) {
    if (saving || busy || submitting) return;
    try { if (dirty) await saveDraft(); } catch (failure) { setError((failure as Error).message); return; }
    if (!mounted.current) return;
    clearProject();
    if (kind === "source") setSourceId(id); else setCampaignId(id);
  }
  async function previewShot(shot: Shot) {
    try {
      setPreviewShotId(shot.id); setPreviewTime(shot.start);
      const url = await asset(shot.source_id);
      if (previewUrl !== url) setPreviewUrl(url);
      else if (sourceVideo.current) { sourceVideo.current.currentTime = shot.start; sourceVideo.current.pause(); }
      sourceVideo.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    } catch (failure) { notify((failure as Error).message); }
  }
  async function uploadFootage(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]; if (!file) return;
    if (!uploadRights || uploadNote.trim().length < 8) { setError("Confirm ownership and provide a rights note before importing original footage."); event.target.value = ""; return; }
    setUploading(true); setError("");
    try { const form = new FormData(); form.append("file", file); form.append("rights_confirmed", "true"); form.append("rights_note", uploadNote); form.append("source_role", "original_creator"); const added = await api("/sources", { method: "POST", body: form }); setSources(current => [added, ...current.filter(item => item.id !== added.id)]); setOriginalIds(current => [...new Set([...current, added.id])]); editRevision.current += 1; setDirty(!!concept); notify("Original footage imported with its rights note. It is available in the storyboard source selector."); }
    catch (failure) { setError((failure as Error).message); }
    finally { setUploading(false); event.target.value = ""; }
  }
  async function render() {
    if (!source || !campaign || !concept || submitting || saving || busy) return;
    setError("");
    setSubmitting(true);
    try {
      const edited = { ...concept, manual_decisions: manualNote };
      const checks = validateConcept(edited, availableSources, rules);
      if (!checks.render_allowed) throw new Error(checks.checks.filter(check => check.status === "FAIL").map(check => check.detail).join(" ") || "Resolve blocking storyboard and campaign checks before rendering.");
      await saveDraft();
      const plan = toEditPlan(edited, source, rules);
      const job = await api("/jobs", { method: "POST", body: JSON.stringify({ source_id: source.id, campaign_id: campaign.id, mode: exportMode, clip_count: 1, plan, director: { project_id: projectId, concept_id: concept.id, manual_decision_note: manualNote } }) });
      setRenderJob(job); notify("Storyboard queued for a real local render. Keep the app open until it finishes.");
    } catch (failure) { setError((failure as Error).message); }
    finally { setSubmitting(false); }
  }
  function undoEdit() { if (!concept || !undo.length || saving || busy || submitting) return; editRevision.current += 1; const previous = undo[undo.length - 1]; setRedo(current => [...current, clone(concept)]); setUndo(undo.slice(0, -1)); setDraft(previous); setDirty(true); }
  function redoEdit() { if (!concept || !redo.length || saving || busy || submitting) return; editRevision.current += 1; const next = redo[redo.length - 1]; setUndo(current => [...current, clone(concept)]); setRedo(redo.slice(0, -1)); setDraft(next); setDirty(true); }
  function applyStyle(id: StyleId) {
    const style = STYLES.find(item => item.id === id);
    if (!style) return;
    editConcept(current => ({ ...current, style_id: id, caption_settings: { ...current.caption_settings, animation: style.caption_animation }, shots: current.shots.map(shot => shot.locked ? shot : { ...shot, composition: style.composition, transition: style.transition, effect: style.effect, manual_modified: true }) }));
  }
  const option = <K extends keyof CreativeOptions>(key: K, value: CreativeOptions[K]) => { if (saving || busy || submitting) return; setOptions(current => ({ ...current, [key]: value })); if (projectId) { setDirty(true); editRevision.current += 1; } };

  return <div className="cd-workspace">
    <div className="cd-mode-banner"><div className="cd-mode-icon"><Clapperboard size={22}/></div><div><strong>Creative direction. Your decisions.</strong><p>Measured frames and supplied captions guide these local suggestions. No paid AI, invented dialogue, or viral predictions.</p></div><span className="cd-local-label"><span/>LOCAL ASSISTED</span></div>
    {error && <div className="cd-error" role="alert"><ShieldCheck size={17}/><span>{error}</span><button type="button" onClick={() => setError("")} aria-label="Dismiss error">×</button></div>}
    <div className="cd-layout">
      <aside className="panel cd-controls"><div className="panel-heading"><div><h2>Direct your next clip</h2><p>GG Pulse Clips · source-first editing</p></div><Focus size={18}/></div><div className="cd-control-body">
        {projects.length > 0 && <label>Saved project<select value={projectId} onChange={event => openProject(event.target.value)}><option value="">New project</option>{projects.map(project => <option key={project.id} value={project.id}>{sources.find(item => item.id === project.source_id)?.filename || "Creative project"} · {date(project.created_at || project.updated_at)}</option>)}</select></label>}
        <label>Source video<select value={sourceId} onChange={event => void changeInput("source", event.target.value)} disabled={busy || saving || submitting}><option value="">Choose authorized footage</option>{sources.map(item => <option key={item.id} value={item.id}>{item.filename}</option>)}</select></label>
        <label>Campaign<select value={campaignId} onChange={event => void changeInput("campaign", event.target.value)} disabled={busy || saving || submitting}><option value="">Choose a campaign brief</option>{campaigns.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        {(!sources.length || !campaigns.length) && !loading && <p className="cd-control-note">Add an authorized source video and campaign brief in Create Clips, then refresh this workspace.</p>}
        <label>Creative mode<select value={options.mode || "assisted"} onChange={event => option("mode", event.target.value as CreativeOptions["mode"])}><option value="assisted">Measured local suggestions</option><option value="manual">Assisted manual editing</option><option disabled>Automatic AI · provider unavailable</option></select></label>
        <label>Editing style<select value={options.style || "auto"} onChange={event => option("style", event.target.value as CreativeOptions["style"])}><option value="auto">Recommend from measured footage</option>{STYLES.map(style => <option key={style.id} value={style.id}>{style.name}</option>)}</select></label>
        <div className="cd-two"><label>Duration preference<input type="number" min="1" max="180" step="1" value={options.duration || 30} onChange={event => option("duration", Number(event.target.value))}/></label><label>Pace<select value={options.pace || "balanced"} onChange={event => option("pace", event.target.value as CreativeOptions["pace"])}><option value="auto">Measured</option><option value="relaxed">Relaxed</option><option value="balanced">Balanced</option><option value="energetic">Energetic</option></select></label></div>
        <label>Target platform<select value={options.platform || "youtube"} onChange={event => { option("platform", event.target.value as Platform); setPlatform(event.target.value as Platform); }}><option value="youtube">YouTube Shorts</option><option value="tiktok">TikTok</option><option value="instagram">Instagram Reels</option></select></label>
        <label>Intended audience<input maxLength={120} value={options.audience || ""} onChange={event => option("audience", event.target.value)} placeholder="Who is this moment for?"/></label>
        <label>Working title<input maxLength={100} value={options.title || ""} onChange={event => option("title", event.target.value)} placeholder="Describe only what the source supports"/></label>
        <div className="cd-two"><label>Source audio<select value={options.audio || "source"} onChange={event => option("audio", event.target.value as "source" | "mute")}><option value="source">Keep original audio</option><option value="mute">Mute audio</option></select></label><label>Export size<select value={options.output_height || 1920} onChange={event => option("output_height", Number(event.target.value) as CreativeOptions["output_height"])}><option value="1920">1080 × 1920</option><option value="1280">720 × 1280</option><option value="960">540 × 960</option></select></label></div>
        <p className="cd-control-note">These preferences apply to new concepts. Edit the selected concept below after generation. Background music and synthetic voices are not added.</p>
        <button className="button primary cd-generate" onClick={() => void generate()} disabled={busy || !source || !campaign || uploading}>{busy ? <LoaderCircle className="spin" size={16}/> : <WandSparkles size={16}/>} {busy ? "Reading your footage…" : "Generate concepts"}<ArrowRight size={15}/></button>
        {busy && <div className="cd-analysis-progress"><div><span>{stage || "Preparing measured analysis"}</span><strong>{Math.round(progress)}%</strong></div><div className="progress-track"><span style={{ width: `${progress}%` }}/></div><button className="text-button" onClick={() => abort.current?.abort()}>Cancel analysis</button></div>}
        <button className="text-button cd-refresh" onClick={() => void loadWorkspace()} disabled={busy}><RefreshCw size={12}/>Refresh library</button>
        <details className="cd-original"><summary><UploadCloud size={14}/>Original creator footage<ChevronDown size={13}/></summary><p>Add permitted original footage for a reaction, comparison, or missing campaign requirement.</p>{sources.filter(item => item.id !== sourceId).map(item => <label className="cd-checkbox" key={item.id}><input type="checkbox" checked={originalIds.includes(item.id)} disabled={busy || saving || submitting} onChange={event => { setOriginalIds(current => event.target.checked ? [...current, item.id] : current.filter(id => id !== item.id)); editRevision.current += 1; if (concept) setDirty(true); }}/><span>{item.filename}</span></label>)}<label className="cd-checkbox"><input type="checkbox" checked={uploadRights} onChange={event => setUploadRights(event.target.checked)}/><span>I own or have permission to edit and republish this footage.</span></label><label>Rights evidence<input value={uploadNote} onChange={event => setUploadNote(event.target.value)} minLength={8} maxLength={1000} placeholder="Ownership or permission reference"/></label><label className={`button secondary cd-file-button ${uploading ? "disabled" : ""}`}><Plus size={14}/>{uploading ? "Importing…" : "Import original footage"}<input type="file" accept="video/mp4,video/quicktime,video/webm,video/x-matroska" disabled={busy || saving || submitting || uploading || !uploadRights || uploadNote.trim().length < 8} onChange={uploadFootage}/></label></details>
      </div></aside>

      <div className="cd-main">
        <section className="panel cd-source-panel"><div className="panel-heading"><div><h2><Video size={16}/>Source workspace</h2><p>{source ? `${source.filename} · ${source.media_info.width} × ${source.media_info.height} · ${time(source.media_info.duration)}` : "Select footage to begin"}</p></div>{source && <span className="cd-source-rights"><ShieldCheck size={12}/>Rights recorded</span>}</div><div className="cd-source-content"><div className="cd-video-wrap">{previewUrl ? <video ref={sourceVideo} src={previewUrl} controls playsInline preload="metadata" onLoadedMetadata={() => { if (sourceVideo.current) sourceVideo.current.currentTime = previewTime; }}/> : <div className="cd-video-empty"><Film size={31}/><strong>Your footage leads the edit</strong><span>No stock scenes or fabricated moments.</span></div>}{previewShotId && <span className="cd-preview-label">Storyboard source preview · {time(previewTime)}</span>}</div><div className="cd-source-facts"><span className="cd-tiny-label">WHAT THE APP CAN VERIFY</span><div><ImageIcon size={16}/><span>Measured visual changes<small>{analysis ? `${analysis.frames.length} frames · ${analysis.scene_changes.length} change points` : "Representative frame sampling"}</small></span></div><div><FileCheck2 size={16}/><span>Supplied caption cues<small>{analysis?.cues.length ? `${analysis.cues.length} user-supplied cues` : "No automatic speech transcription"}</small></span></div><div><ShieldCheck size={16}/><span>Context needs your review<small>Objects, reactions, claims, and outcomes are not inferred.</small></span></div>{analysis && <details><summary>Analysis limits</summary>{[...analysis.limitations, ...analysis.warnings].map((item, index) => <p key={index}>{item}</p>)}</details>}</div></div></section>

        {replaceRequested && <div className="cd-replace-prompt"><Save size={18}/><span><strong>Keep your manual work.</strong> The current edit will be saved before a new concept set is created. Earlier projects remain available.</span><button className="button secondary small-button" onClick={() => setReplaceRequested(false)}>Keep editing</button><button className="button primary small-button" onClick={() => void generate(true)}>Save & create new concepts</button></div>}

        {!batch ? <section className="panel cd-concept-empty"><span className="cd-section-icon"><Layers3 size={25}/></span><h2>Three directions. One authentic source.</h2><p>Local measurements and existing captions help build distinct starting points. You decide which story the actual footage can support.</p><div className="cd-direction-list">{[{ title: "High engagement", text: "A direct opening and concise, focused pacing.", icon: Gauge }, { title: "Cinematic", text: "Room for composition and deliberate timing.", icon: Film }, { title: "Creative storytelling", text: "Context, development, and a clear endpoint.", icon: Layers3 }].map((item, index) => <div key={item.title}><span>0{index + 1}</span><item.icon size={19}/><strong>{item.title}</strong><small>{item.text}</small></div>)}</div><p className="cd-footnote">Short or repetitive sources may provide fewer meaningful concepts. A different font or color does not count as a new idea.</p></section> : <>
          <section className="cd-concept-section"><div className="cd-section-heading"><div><span className="cd-tiny-label">SOURCE-BACKED STARTING POINTS</span><h2>Choose your creative direction</h2></div><span>{batch.concepts.length} concept{batch.concepts.length === 1 ? "" : "s"}</span></div><div className="cd-concept-grid">{batch.concepts.map((item, index) => <button key={item.id} className={`panel cd-concept-card ${selectedId === item.id ? "selected" : ""}`} disabled={busy || saving || submitting} onClick={() => selectConcept(item)}><div className="cd-concept-image">{item.shots[0]?.thumbnail ? <img src={item.shots[0].thumbnail} alt={`Measured source frame for ${item.title}`}/> : <Film size={25}/>}<span className="cd-card-number">0{index + 1}</span><span className="cd-card-time">{duration(item).toFixed(1)}s</span>{batch.recommended_id === item.id && <span className="cd-recommended"><Sparkles size={10}/>Local recommendation</span>}</div><div className="cd-concept-body"><span className="cd-tiny-label">{kindLabel(item.kind)}</span><h3>{item.title}</h3><p>{item.distinct_reason}</p><div><span>{item.shots.length} source shots</span><span>{selectedId === item.id ? <><Check size={12}/>Selected</> : <>Inspect<ArrowRight size={12}/></>}</span></div></div></button>)}</div>{batch.recommendation && <div className="cd-recommendation"><Sparkles size={15}/><p>{batch.recommendation}<small>Explainable editing guidance, not a prediction of views or retention.</small></p></div>}{batch.unavailable_reasons.length > 0 && <div className="cd-limits">{batch.unavailable_reasons.map((item, index) => <p key={index}>{item}</p>)}</div>}</section>

          {concept && <><section className="panel cd-storyboard"><div className="panel-heading"><div><h2><Scissors size={16}/>Editable storyboard</h2><p>{concept.audience || "Review the intended audience"} · {duration(concept).toFixed(1)} seconds · {dirty ? "Unsaved edits" : "Saved version"}</p></div><div className="cd-editor-actions"><button className="icon-button" onClick={undoEdit} disabled={!undo.length} aria-label="Undo storyboard edit"><Undo2 size={16}/></button><button className="icon-button" onClick={redoEdit} disabled={!redo.length} aria-label="Redo storyboard edit"><Redo2 size={16}/></button><button className="button secondary small-button" onClick={() => void save()} disabled={saving || busy || submitting}><Save size={13}/>Save</button></div></div>
            <div className="cd-concept-controls"><div className="cd-three"><label>Selected concept style<select value={concept.style_id} onChange={event => applyStyle(event.target.value as StyleId)}>{STYLES.map(style => <option key={style.id} value={style.id}>{style.name}</option>)}</select></label><label>Concept audio<select value={concept.audio_treatment} onChange={event => editConcept({ audio_treatment: event.target.value as CreativeConcept["audio_treatment"] })}><option value="source">Keep source audio</option><option value="mute">Mute audio</option></select></label><label>Concept output size<select value={concept.output_height} onChange={event => { const height = Number(event.target.value) as CreativeConcept["output_height"]; editConcept({ output_height: height, output_width: (height === 1920 ? 1080 : height === 1280 ? 720 : 540) as CreativeConcept["output_width"] }); }}><option value="1920">1080 × 1920</option><option value="1280">720 × 1280</option><option value="960">540 × 960</option></select></label></div><p>Applying a style updates unlocked shots and caption animation. Locked shots retain their framing and effects. Split-screen styles require separately permitted secondary footage.</p><label>Publication title<input maxLength={100} value={concept.selected_title} onChange={event => editConcept({ selected_title: event.target.value })}/></label><label>Publication description<textarea maxLength={2000} rows={3} value={concept.description} onChange={event => editConcept({ description: event.target.value })} placeholder="Describe only what the footage supports. Required campaign text is retained in the upload package."/></label><label>Topic hashtags<input key={concept.id + concept.hashtags.join(" ")} defaultValue={concept.hashtags.join(" ")} onBlur={event => { const hashtags = event.target.value.split(/\s+/).filter(Boolean); if (hashtags.join(" ") !== concept.hashtags.join(" ")) editConcept({ hashtags }); }} placeholder="#topic #campaign"/></label></div><div className="cd-story-intro"><div><label>Opening hook<input value={concept.hook} maxLength={140} onChange={event => editConcept({ hook: event.target.value })}/></label><small>{concept.hook_assessment.warning}</small>{concept.hook_alternatives.length > 0 && <div className="cd-hook-alternatives">{concept.hook_alternatives.map((hook, index) => <button key={index} onClick={() => editConcept({ hook })}>{hook}</button>)}</div>}</div><div className="cd-hook-assessment"><span>Explainable hook assessment</span><strong>{concept.hook_assessment.score}<small>/100</small></strong><p>Heuristic · {concept.hook_assessment.accuracy.replaceAll("_", " ")}</p><details><summary>Why this assessment?</summary>{concept.hook_assessment.factors.map(factor => <p key={factor.name}><b>{factor.name}: {factor.score}</b><br/>{factor.explanation}</p>)}</details></div></div>
            <div className="cd-shot-list">{concept.shots.map((shot, index) => <article className={`cd-shot ${previewShotId === shot.id ? "previewing" : ""}`} key={shot.id}><div className="cd-shot-head"><span className="cd-shot-order">{String(index + 1).padStart(2, "0")}</span><label>Story role<select value={shot.role} disabled={shot.locked} onChange={event => editShot(shot.id, { role: event.target.value as Shot["role"] })}>{["hook", "context", "development", "payoff"].map(role => <option key={role}>{role}</option>)}</select></label><span className="cd-shot-range">{time(shot.start)} → {time(shot.end)}</span><div className="cd-shot-actions"><button className="icon-button" aria-label={`Preview shot ${index + 1}`} onClick={() => void previewShot(shot)}><Play size={14}/></button><button className="icon-button" aria-label={`Move shot ${index + 1} earlier`} disabled={index === 0 || shot.locked} onClick={() => editConcept(current => { const list = [...current.shots]; [list[index - 1], list[index]] = [list[index], list[index - 1]]; return { ...current, shots: list }; })}><ArrowUp size={14}/></button><button className="icon-button" aria-label={`Move shot ${index + 1} later`} disabled={index === concept.shots.length - 1 || shot.locked} onClick={() => editConcept(current => { const list = [...current.shots]; [list[index + 1], list[index]] = [list[index], list[index + 1]]; return { ...current, shots: list }; })}><ArrowDown size={14}/></button><button className={`icon-button ${shot.locked ? "cd-locked" : ""}`} aria-label={shot.locked ? `Unlock shot ${index + 1}` : `Lock shot ${index + 1}`} onClick={() => editShot(shot.id, { locked: !shot.locked })}><LockKeyhole size={13}/></button><button className="icon-button" aria-label={`Remove shot ${index + 1}`} disabled={concept.shots.length <= 1 || shot.locked} onClick={() => editConcept(current => ({ ...current, shots: current.shots.filter(item => item.id !== shot.id) }))}><Trash2 size={13}/></button></div></div>
              <div className="cd-shot-body"><button className="cd-shot-thumbnail" onClick={() => void previewShot(shot)} aria-label={`Preview source for shot ${index + 1}`}>{shot.thumbnail ? <img src={shot.thumbnail} alt={`Source frame at ${time(shot.start)}`}/> : <Film size={22}/>}<span><Play size={12}/>Source preview</span></button><div className="cd-shot-fields"><label>Footage<select value={shot.source_id} disabled={shot.locked} onChange={event => { const next = sources.find(item => item.id === event.target.value); if (next) editShot(shot.id, { source_id: next.id, start: 0, end: Math.min(next.media_info.duration, shot.end - shot.start), thumbnail: "", source_evidence: ["User replaced the source footage. Review context manually."] }); }}>{sources.map(item => <option key={item.id} value={item.id}>{item.filename}</option>)}</select></label><div className="cd-three"><label>Start seconds<input type="number" min="0" step="0.01" value={shot.start} disabled={shot.locked} onChange={event => editShot(shot.id, { start: Number(event.target.value) })}/></label><label>End seconds<input type="number" min="0" step="0.01" value={shot.end} disabled={shot.locked} onChange={event => editShot(shot.id, { end: Number(event.target.value) })}/></label><label>Transition<select value={shot.transition} disabled={shot.locked} onChange={event => editShot(shot.id, { transition: event.target.value as Shot["transition"] })}><option value="cut">Cut</option><option value="fade">Short fade</option></select></label></div><label>Contextual text <span>optional · source-supported only</span><input maxLength={140} value={shot.overlay_text} disabled={shot.locked} onChange={event => editShot(shot.id, { overlay_text: event.target.value })}/></label><details className="cd-shot-details"><summary>Framing, composition & effects<ChevronDown size={12}/></summary><div className="cd-three"><label>Crop X (0–1)<input type="number" min="0" max="1" step="0.05" value={shot.crop_x} disabled={shot.locked} onChange={event => editShot(shot.id, { crop_x: Number(event.target.value) })}/></label><label>Crop Y (0–1)<input type="number" min="0" max="1" step="0.05" value={shot.crop_y} disabled={shot.locked} onChange={event => editShot(shot.id, { crop_y: Number(event.target.value) })}/></label><label>Zoom (1–1.5)<input type="number" min="1" max="1.5" step="0.05" value={shot.zoom} disabled={shot.locked} onChange={event => editShot(shot.id, { zoom: Number(event.target.value) })}/></label></div><div className="cd-two"><label>Composition<select value={shot.composition} disabled={shot.locked} onChange={event => editShot(shot.id, { composition: event.target.value as Shot["composition"] })}><option value="fill">Full-frame crop</option><option value="fit_blur">Fit with soft background</option><option value="split">Split screen</option></select></label><label>Source treatment<select value={shot.effect} disabled={shot.locked} onChange={event => editShot(shot.id, { effect: event.target.value as Shot["effect"] })}><option value="none">Natural</option><option value="contrast">Contrast</option><option value="retro">Retro</option></select></label></div>{shot.composition === "split" && <div className="cd-two"><label>Secondary footage<select value={shot.secondary_source_id || ""} disabled={shot.locked} onChange={event => editShot(shot.id, { secondary_source_id: event.target.value || undefined, secondary_start: 0 })}><option value="">Select permitted footage</option>{sources.filter(item => item.id !== shot.source_id).map(item => <option key={item.id} value={item.id}>{item.filename}</option>)}</select></label><label>Secondary start<input type="number" min="0" step="0.01" value={shot.secondary_start || 0} disabled={shot.locked} onChange={event => editShot(shot.id, { secondary_start: Number(event.target.value) })}/></label></div>}<label className="cd-checkbox"><input type="checkbox" checked={shot.crop_x_end !== undefined} disabled={shot.locked} onChange={event => editShot(shot.id, event.target.checked ? { crop_x_end: shot.crop_x, crop_y_end: shot.crop_y } : { crop_x_end: undefined, crop_y_end: undefined })}/><span>Animate the crop toward a manual endpoint</span></label>{shot.crop_x_end !== undefined && <div className="cd-two"><label>End crop X<input type="number" min="0" max="1" step="0.05" value={shot.crop_x_end} disabled={shot.locked} onChange={event => editShot(shot.id, { crop_x_end: Number(event.target.value) })}/></label><label>End crop Y<input type="number" min="0" max="1" step="0.05" value={shot.crop_y_end ?? shot.crop_y} disabled={shot.locked} onChange={event => editShot(shot.id, { crop_y_end: Number(event.target.value) })}/></label></div>}<p>{shot.rationale}</p>{shot.source_evidence.map((evidence, evidenceIndex) => <small key={evidenceIndex}>{evidence}</small>)}</details></div></div>
            </article>)}</div><div className="cd-add-shot"><button className="button secondary small-button" onClick={() => { if (!source) return; editConcept(current => ({ ...current, shots: [...current.shots, { id: crypto.randomUUID(), source_id: source.id, role: "development", start: 0, end: Math.min(3, source.media_info.duration), crop_x: .5, crop_y: .5, zoom: 1, composition: "fill", transition: "cut", effect: "none", overlay_text: "", overlay_position: "top", rationale: "User added a source shot. Review its role in the story.", source_evidence: ["Manual selection"], thumbnail: "", manual_modified: true }] })); }} disabled={concept.shots.length >= 20}><Plus size={14}/>Add a source shot</button><span>{concept.ending_strategy}</span></div>
            <div className="cd-caption-controls"><div className="cd-section-heading"><h3>Caption & brand treatment</h3><span>GG Pulse Clips</span></div><label className="cd-checkbox"><input type="checkbox" checked={concept.caption_settings.enabled} onChange={event => editConcept({ caption_settings: { ...concept.caption_settings, enabled: event.target.checked } })}/><span>Show supplied source captions</span></label><div className="cd-three"><label>Animation<select value={concept.caption_settings.animation} onChange={event => editConcept({ caption_settings: { ...concept.caption_settings, animation: event.target.value as CaptionSettings["animation"] } })}>{["none", "fade", "pop", "slide"].map(item => <option key={item}>{item}</option>)}</select></label><label>Position<select value={concept.caption_settings.position} onChange={event => editConcept({ caption_settings: { ...concept.caption_settings, position: event.target.value as CaptionSettings["position"] } })}><option value="lower">Lower safe zone</option><option value="upper">Upper safe zone</option><option value="center">Center · review footage</option></select></label><label>Font size<input type="number" min="54" max="90" value={concept.caption_settings.font_size} onChange={event => editConcept({ caption_settings: { ...concept.caption_settings, font_size: Number(event.target.value) } })}/></label></div><div className="cd-three"><label>Caption color<input type="color" value={concept.caption_settings.color} onChange={event => editConcept({ caption_settings: { ...concept.caption_settings, color: event.target.value } })}/></label><label>Top safe margin<input type="number" min="180" max="480" value={concept.caption_settings.safe_top} onChange={event => editConcept({ caption_settings: { ...concept.caption_settings, safe_top: Number(event.target.value) } })}/></label><label>Bottom safe margin<input type="number" min="220" max="550" value={concept.caption_settings.safe_bottom} onChange={event => editConcept({ caption_settings: { ...concept.caption_settings, safe_bottom: Number(event.target.value) } })}/></label></div><p>Uploaded cues retain their supplied timing. Word-level highlighting is unavailable without verified word timestamps. Check every caption against the actual footage and campaign.</p></div>
          </section>

          <div className="cd-bottom-grid"><section className="panel cd-preflight"><div className="panel-heading"><h2><ShieldCheck size={16}/>Campaign preflight</h2>{preflight && <Status value={preflight.status}/>}</div><div className="cd-preflight-body">{preflight?.assisted_manual_required && <div className="cd-manual-required"><LockKeyhole size={16}/><div><strong>Assisted manual editing required</strong><p>Campaign restrictions require your creative decisions and evidence. A render is not a compliant submission.</p></div></div>}<label>Your creative decisions & evidence<textarea value={manualNote} rows={3} maxLength={4000} onChange={event => { setManualNote(event.target.value); editRevision.current += 1; setDirty(true); }} placeholder="Explain the source choices, edits you made, campaign checks, and any original-footage reference."/></label>{preflight?.missing_footage?.length ? <div className="cd-missing">{preflight.missing_footage.map((item, index) => <p key={index}>{item}</p>)}</div> : null}<div className="cd-check-list">{preflight?.checks.map((check, index) => <div key={`${check.rule}-${index}`}><span className={`cd-check-dot ${check.status.toLowerCase()}`}/><div><strong>{check.rule.replaceAll("_", " ")}</strong><p>{check.detail}</p><small>{check.classification}</small></div><Status value={check.status}/></div>)}</div></div></section>
          <section className="panel cd-export"><div className="panel-heading"><h2><ArrowDownToLine size={16}/>Local export</h2><span className="cd-local-label">NO PAID API</span></div><div className="cd-export-body"><div className="cd-output-size"><Film size={28}/><div><strong>{concept.output_width} × {concept.output_height}</strong><span>{duration(concept).toFixed(1)} seconds · vertical MP4</span></div></div><label>Export mode<select value={exportMode} onChange={event => setExportMode(event.target.value)}><option value="fast">Fast Export · quicker CPU encoding</option><option value="quality">Premium Export · higher encoding quality</option></select></label><p>Uses the existing FFmpeg renderer. Keep the tab open. A lower source quality may need a smaller output; inspect the actual file before publishing.</p><button className="button primary cd-render" disabled={busy || saving || submitting || uploading || !preflight?.render_allowed || !!renderJob && ["queued", "processing"].includes(renderJob.status)} onClick={() => void render()}><Clapperboard size={16}/>Render selected concept<ArrowRight size={15}/></button>{preflight?.status !== "PASS" && <small>Unverified semantic checks remain REVIEW REQUIRED after rendering. They are never automatically approved.</small>}{renderJob && <div className={`cd-render-job ${renderJob.status}`}><div><strong>{String(renderJob.status).replaceAll("_", " ")}</strong><span>{renderJob.progress || 0}%</span></div><div className="progress-track"><span style={{ width: `${renderJob.progress || 0}%` }}/></div><p>{renderJob.error || renderJob.stage}</p>{renderJob.status === "completed" && <button className="button secondary small-button" onClick={onRendered}>Open exported clips<ArrowRight size={13}/></button>}</div>}</div></section></div>

          <section className="panel cd-publishing"><div className="panel-heading"><div><h2><Copy size={16}/>Publishing assistant</h2><p>Grounded suggestions for your reviewed concept. Edit before posting.</p></div><div className="cd-platform-tabs">{(["youtube", "tiktok", "instagram"] as Platform[]).map(item => <button key={item} className={platform === item ? "active" : ""} onClick={() => { setPlatform(item); setPublishingIndex(0); }}>{item === "youtube" ? "Shorts" : item === "tiktok" ? "TikTok" : "Reels"}</button>)}</div></div><div className="cd-publishing-body"><div className="cd-publishing-options">{(suggestions as Row)?.variants?.map((variant: Row, index: number) => <button key={index} className={publishingIndex === index ? "selected" : ""} onClick={() => setPublishingIndex(index)}><span>0{index + 1}</span><strong>{variant.title || variant.opening_hook}</strong><small>{variant.strategy}</small></button>)}</div>{(suggestions as Row)?.variants?.[publishingIndex] && <PublishingDetails variant={(suggestions as Row).variants[publishingIndex]} notify={notify}/>}<div className="cd-publishing-note"><ShieldCheck size={14}/>Required campaign text takes priority. These suggestions do not publish, submit, verify claims, or predict performance.</div></div></section>
          </>}
        </>}
      </div>
    </div>
  </div>;
}

function PublishingDetails({ variant, notify }: { variant: Row; notify: (message: string) => void }) {
  return <div className="cd-publishing-detail"><div><label>Description / caption</label><p>{variant.description || variant.caption || "Add a description supported by the actual clip."}</p></div><div><label>Hashtags</label><p className="cd-tags">{(variant.hashtags || []).join(" ") || "No supplied topic tags."}</p></div><div className="cd-cover"><ImageIcon size={15}/><span>Suggested source cover: {time(Number(variant.cover_timestamp || 0))}<small>Review the actual frame before choosing a cover.</small></span><button className="button secondary small-button" onClick={async () => { try { await navigator.clipboard.writeText([variant.title, variant.description || variant.caption, (variant.hashtags || []).join(" ")].filter(Boolean).join("\n\n")); notify("Publishing suggestion copied. Review the text before posting."); } catch { notify("Copy was unavailable. Select and copy the text manually."); } }}><Copy size={13}/>Copy suggestion</button></div></div>;
}
