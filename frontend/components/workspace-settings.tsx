"use client";

import { Cloud, FileText, Gauge, LogOut, Settings2, ShieldCheck, SlidersHorizontal } from "lucide-react";

type Row = Record<string, any>;
type Props = { config: Row; freeMode: boolean; localNoAuth: boolean; aiReady: boolean; user: Row | null; refresh: () => void; notify: (message: string) => void; signIn: () => void; signOut: () => Promise<void> };

export default function WorkspaceSettings({ config, freeMode, localNoAuth, aiReady, user, signIn, signOut }: Props) {
  const ffmpegReady = config.ffmpeg === true || config.ffmpeg?.configured;
  const browserMode = config.browser_mode === true;
  const services = freeMode ? [
    { name: "Local FFmpeg rendering", ready: ffmpegReady, label: ffmpegReady ? "Ready" : browserMode ? "Loads on render" : "Checking", detail: browserMode ? "Video encoding runs in this browser. Keep the app open while rendering." : "Native FFmpeg encodes on this computer, using a supported hardware encoder when available." },
    { name: "Paid AI requests", ready: true, label: "Blocked", detail: "Paid cloud AI is blocked. Native footage analysis, speech transcription and metadata use your installed local models; no paid API key is required." },
    { name: "Source and clip storage", ready: true, label: browserMode ? "This browser" : "Local disk", detail: browserMode ? "Source files and project records are stored in this browser on your device." : "Original videos, render versions, and project records are saved on this computer." },
    { name: "Optional subtitles", ready: true, label: "SRT / VTT", detail: "Upload an existing caption file. Native creation can transcribe speech locally. The browser edition uses supplied subtitle cues." },
  ] : [
    { name: "Hosted AI provider", ready: aiReady, label: aiReady ? "Configured" : "Setup needed", detail: "Optional hosted campaign analysis, transcription, and metadata. This mode can incur provider charges." },
    { name: "FFmpeg rendering", ready: ffmpegReady, label: ffmpegReady ? "Configured" : "Setup needed", detail: "CPU-based rendering with source and editing-version preservation." },
    { name: "Storage", ready: true, label: config.storage === "s3" ? "S3" : "Local disk", detail: "Storage follows the deployment configuration." },
  ];
  return <div className="settings-layout">
    <section className="panel">
      <div className="panel-heading"><div><h2>{freeMode ? "Free local processing" : "Processing services"}</h2><p>{freeMode ? "Your editing workflow has no paid AI dependency." : "Services are configured through deployment settings."}</p></div>{freeMode ? <Gauge size={20}/> : <Cloud size={20}/>}</div>
      {services.map(service => <div className="service-row" key={service.name}><span className={"service-dot " + (service.ready ? "ready" : "")}/><div><strong>{service.name}</strong><p>{service.detail}</p></div><span className={"badge " + (service.ready ? "mint" : "neutral")}><span/>{service.label}</span></div>)}
      <div className="notice muted settings-note"><FileText size={17}/><span>{freeMode ? "Local creation handles analysis and metadata automatically when local models are installed. You can edit each clip before publishing. The browser edition provides manual clipping and measured concepts." : "See README.md and .env.example for optional hosted-provider configuration."}</span></div>
    </section>
    <div>
      <section className="panel"><div className="panel-heading"><h2>Workspace</h2><SlidersHorizontal size={17}/></div><div className="settings-details">
        <label>Access<span>{localNoAuth ? "Open local workspace · no login" : user?.email || "Not signed in"}</span></label>
        <label>Clip selection<span>{freeMode ? browserMode ? "Manual timing and measured concepts" : "Local AI with optional manual edits" : "Hosted analysis"}</span></label>
        <label>Software / AI processing fees<span>{freeMode ? "$0 · paid AI blocked" : "See configured provider"}</span></label>
        <label>Publishing<span>Review and authorize every post</span></label>
        <p>{freeMode ? "This mode uses the device you already have. It does not purchase API credits or require a paid cloud host. Local files and browser storage should be backed up before clearing data." : "Credentials remain on the server. Review spending controls and provider billing before enabling hosted processing."}</p>
        {localNoAuth ? <div className="info-line"><Settings2 size={15}/>Your workspace opens directly. No password or account is needed.</div> : user ? <button className="button secondary" onClick={signOut}><LogOut size={15}/>Sign out</button> : <button className="button secondary" onClick={signIn}>Sign in</button>}
      </div></section>
      <p>Remotion is free for individuals and eligible small organizations. Its browser renderer sends usage telemetry; it does not upload your video. <a href="https://www.remotion.dev/pricing" target="_blank" rel="noreferrer">License terms</a></p><div className="rights-card"><ShieldCheck size={22}/><h3>Your sources. Your rights.</h3><p>Use videos you own or have permission to edit and republish. Each upload keeps your authorization note.</p></div>
    </div>
  </div>;
}
