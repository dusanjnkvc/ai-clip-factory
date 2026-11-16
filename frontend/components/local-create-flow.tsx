"use client";

import { useEffect, useState, type FormEvent } from "react";
import { ArrowRight, CircleHelp, FileCheck2, FileText, LoaderCircle, Plus, Scissors, ShieldCheck, UploadCloud, Video, X } from "lucide-react";
import { api } from "@/lib/api";

type Row = Record<string, any>;
type Props = { campaignOnly: boolean; campaigns: Row[]; sources: Row[]; onDone: (message: string) => void };

export default function LocalCreateFlow({ campaignOnly, campaigns, sources, onDone }: Props) {
  const [mode, setMode] = useState("fast");
  const [campaignId, setCampaignId] = useState("");
  const [general, setGeneral] = useState(false);
  const [sourceId, setSourceId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [attachment, setAttachment] = useState<File | null>(null);
  const [subtitles, setSubtitles] = useState<File | null>(null);
  const [subtitleText,setSubtitleText]=useState("");
  const [subtitleFormat,setSubtitleFormat]=useState("srt");
  const [rights, setRights] = useState(false);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState("");
  const [error, setError] = useState("");
  const [drag, setDrag] = useState(false);
  const [uploadedSubtitle, setUploadedSubtitle] = useState("");
  const [preview, setPreview] = useState("");
  const selectedSource = sources.find(source => source.id === sourceId);

  useEffect(() => {
    if (!file) { setPreview(""); return; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      let cid = campaignId;
      if (!cid) {
        setStage("Saving your campaign brief…");
        const campaign = await api("/campaigns", { method: "POST", body: JSON.stringify({
          name: form.get("name") || "General clipping",
          brief: form.get("brief") || "General authorized video clipping. No external campaign requirements supplied.",
          url: form.get("url") || null,
        }) });
        cid = campaign.id;
        setCampaignId(cid);
        if (attachment) {
          setStage("Saving campaign attachment…");
          const upload = new FormData();
          upload.append("file", attachment);
          await api("/campaigns/" + cid + "/attachments", { method: "POST", body: upload });
        }
      }
      if (campaignOnly) {
        onDone("Campaign saved. Review the supplied requirements against the original brief before publishing.");
        return;
      }
      let sid = sourceId;
      if (!sid) {
        if (!file || !rights) throw new Error("Upload an authorized video and confirm your source rights.");
        setStage("Uploading and validating source video…");
        const upload = new FormData();
        upload.append("file", file);
        upload.append("rights_confirmed", "true");
        upload.append("rights_note", String(form.get("rights_note") || "I own this source or have explicit permission to edit and republish it."));
        const source = await api("/sources", { method: "POST", body: upload });
        sid = source.id;
        setSourceId(sid);
      }
      const captionFile=subtitles || (subtitleText.trim()?new File([subtitleText],"pasted-subtitles."+subtitleFormat,{type:"text/plain"}):null);
      if (captionFile) {
        const identity = sid + ":" + captionFile.name + ":" + (subtitles?subtitles.lastModified:subtitleText);
        if (uploadedSubtitle !== identity) {
          setStage("Importing your subtitle timestamps…");
          const upload = new FormData();
          upload.append("file", captionFile);
          await api("/sources/" + sid + "/subtitles", { method: "POST", body: upload });
          setUploadedSubtitle(identity);
        }
      }
      const start = Number(form.get("start") || 0);
      const endValue = String(form.get("end") || "").trim();
      const end = endValue ? Number(endValue) : null;
      if (end !== null && end <= start) throw new Error("End time must be after start time.");
      setStage("Adding your clip to the local render queue…");
      await api("/jobs", { method: "POST", body: JSON.stringify({
        campaign_id: cid, source_id: sid, mode, clip_count: 1,
        manual_selection: {
          start, end,
          title: String(form.get("title") || ""),
          description: String(form.get("description") || ""),
          hashtags: String(form.get("hashtags") || "").split(/\s+/).filter(Boolean),
          crop_x: Number(form.get("crop_x") ?? 0.5),
          crop_y: Number(form.get("crop_y") ?? 0.5),
          zoom: Number(form.get("zoom") || 1),
          subtitle_style: String(form.get("subtitle_style") || "clean"),
          hook: "", show_hook: false,
        },
      }) });
      onDone("Local render queued. Your computer will create the MP4; review its captions, crop, and compliance when ready.");
    } catch (failure) { setError((failure as Error).message); }
    finally { setBusy(false); setStage(""); }
  }

  return <form onSubmit={submit} className="form-body create-form">
    <div className="notice local-mode-notice"><ShieldCheck size={18}/><span><strong>Free local mode · no paid API calls</strong><br/>You choose the moment and metadata. FFmpeg renders it on your computer. Automatic transcription and AI moment selection are unavailable.</span></div>
    {!campaignOnly && <div className="segmented"><button type="button" className={!general ? "selected" : ""} onClick={() => setGeneral(false)}><FileCheck2 size={15}/>Content Rewards</button><button type="button" className={general ? "selected" : ""} onClick={() => { setGeneral(true); setCampaignId(""); }}><Scissors size={15}/>General clipping</button></div>}
    <div className="form-section-title"><span>01</span>{general ? "Your project" : "Campaign brief"}<small>Keep the source of every rule</small></div>
    {!campaignOnly && campaigns.length > 0 && !general && <label>Campaign<select value={campaignId} onChange={event => setCampaignId(event.target.value)}><option value="">Create a new campaign</option>{campaigns.map(campaign => <option key={campaign.id} value={campaign.id}>{campaign.name}</option>)}</select></label>}
    {!campaignId && <>
      <label>{general ? "Project name" : "Campaign name"}<input name="name" placeholder={general ? "Interview highlights" : "Give your campaign a name"} required maxLength={200}/></label>
      {!general && <label>Campaign URL <span className="optional">optional · reference only</span><input type="url" name="url" placeholder="https://…"/><small>Paste the requirements below. Private campaign pages are never scraped.</small></label>}
      <label>{general ? "Project notes" : "Campaign requirements"}<textarea name="brief" rows={5} required={!general} placeholder={general ? "Describe your project and any requirements you want to keep…" : "Paste the full brief, including platforms, duration, required hashtags, disclosures, and submission instructions…"}/></label>
      {!general && <label className="attachment-input"><FileText size={17}/><span>{attachment?.name || "Add a PDF or campaign screenshot"}<small>Saved as evidence. Images need manual reading; no cloud OCR is used.</small></span><input type="file" accept="application/pdf,image/png,image/jpeg" onChange={event => setAttachment(event.target.files?.[0] || null)}/><Plus size={17}/></label>}
    </>}
    {!campaignOnly && <>
      <div className="form-section-title"><span>02</span>Authorized source video<small>Your original is preserved</small></div>
      {sources.length > 0 && <label>Source video<select value={sourceId} onChange={event => setSourceId(event.target.value)}><option value="">Upload a new video</option>{sources.map(source => <option key={source.id} value={source.id}>{source.filename || source.name}</option>)}</select></label>}
      {selectedSource && <div className="info-line"><Video size={15}/>{selectedSource.filename} · {Number(selectedSource.media_info?.duration || 0).toFixed(1)} seconds</div>}
      {!sourceId && <>
        <label className={"dropzone " + (drag ? "dragging " : "") + (file ? "has-file" : "")} onDragOver={event => { event.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={event => { event.preventDefault(); setDrag(false); setFile(event.dataTransfer.files[0] || null); }}><UploadCloud size={29}/><strong>{file ? file.name : "Drop your source video here"}</strong><span>{file ? (file.size / 1024 / 1024).toFixed(1) + " MB · click to replace" : <>or <b>browse files</b> · MP4, MOV, WebM</>}</span><input type="file" accept="video/mp4,video/quicktime,video/webm,video/x-matroska" required={!file} onChange={event => setFile(event.target.files?.[0] || null)}/></label>
        {preview && <div className="source-preview"><video src={preview} controls preload="metadata"/><small>Preview your source and choose its start and end times below.</small></div>}
        <label className="checkbox-label"><input type="checkbox" checked={rights} onChange={event => setRights(event.target.checked)} required/><span>I own this video or have explicit permission to edit and republish it.<small>A public URL alone doesn’t grant usage rights.</small></span></label>
        <label>Rights evidence <span className="optional">optional</span><input name="rights_note" placeholder="License, permission reference, or ownership note"/></label>
      </>}
      <label className="attachment-input"><FileText size={17}/><span>{subtitles?.name || "Add subtitles (optional)"}<small>SRT or VTT · source-video cue times · no automatic transcription</small></span><input type="file" accept=".srt,.vtt,text/vtt,application/x-subrip" onChange={event => setSubtitles(event.target.files?.[0] || null)}/><Plus size={17}/></label>
      {subtitles && <button type="button" className="text-button" onClick={() => setSubtitles(null)}><X size={12}/>Remove selected subtitle file</button>}
      {!subtitles&&<details className="paste-captions"><summary>Or paste existing SRT / VTT captions</summary><label>Caption format<select value={subtitleFormat} onChange={e=>setSubtitleFormat(e.target.value)}><option value="srt">SRT</option><option value="vtt">WebVTT</option></select></label><label>Timed caption text<textarea value={subtitleText} onChange={e=>setSubtitleText(e.target.value)} rows={5} maxLength={1000000} placeholder={"1\n00:00:01,000 --> 00:00:03,000\nYour existing caption"}/></label><small>Paste exact source-video cue times. Speech and word timestamps are not inferred.</small></details>}
      <div className="form-section-title"><span>03</span>Choose your clip<small>One manual selection per render</small></div>
      <div className="generation-settings"><label>Source start (seconds)<input name="start" type="number" min="0" step="0.01" defaultValue="0" required/></label><label>Source end (seconds)<input name="end" type="number" min="0.01" step="0.01" placeholder="Blank = up to 30 seconds after start"/></label></div>
      <div className="info-line"><CircleHelp size={15}/>A blank end uses up to 30 seconds after your start, limited by source length. This is not an AI-selected moment.</div>
      <label>Clip title<input name="title" required maxLength={100} placeholder="Write a title that describes your chosen moment"/></label>
      <label>Description / caption<textarea name="description" rows={3} maxLength={2000} placeholder="Describe the actual clip. Required campaign text is included in the metadata for review."/></label>
      <label>Hashtags<input name="hashtags" maxLength={500} placeholder="#topic #campaign"/><small>Space-separated. Only use relevant tags.</small></label>
      <div className="generation-settings"><label>Horizontal crop (0–1)<input name="crop_x" type="number" min="0" max="1" step="0.05" defaultValue="0.5" required/><small>0 = left, 0.5 = center, 1 = right</small></label><label>Vertical crop (0–1)<input name="crop_y" type="number" min="0" max="1" step="0.05" defaultValue="0.5" required/><small>0 = top, 0.5 = center, 1 = bottom</small></label></div>
      <div className="generation-settings"><label>Zoom<input name="zoom" type="number" min="1" max="1.5" step="0.05" defaultValue="1" required/></label><label>Subtitle style<select name="subtitle_style"><option value="clean">Clean</option><option value="bold">Bold</option><option value="podcast">Podcast</option><option value="gaming">Gaming</option></select></label></div>
      <div className="info-line"><FileText size={15}/>Subtitles use your uploaded cue times. Without a caption file, the clip has no speech captions.</div>
      <label>Encoding mode<select value={mode} onChange={event => setMode(event.target.value)}><option value="fast">FAST — quicker CPU encoding</option><option value="quality">QUALITY — slower CPU encoding</option></select></label>
      <div className="info-line"><ShieldCheck size={15}/>Every render is checked. Semantic campaign requirements still need your review.</div>
    </>}
    {error && <div className="form-error" role="alert">{error}</div>}
    {stage && <div className="info-line"><LoaderCircle size={15} className="spin"/>{stage}</div>}
    <button className="button primary full" disabled={busy}>{busy ? <LoaderCircle size={17} className="spin"/> : campaignOnly ? <FileCheck2 size={17}/> : <Scissors size={17}/>} {busy ? "Working…" : campaignOnly ? "Save campaign" : "Render clip locally"}<ArrowRight size={16}/></button>
    <p className="form-footnote">Nothing is published automatically. Review the actual clip and campaign requirements first.</p>
  </form>;
}
