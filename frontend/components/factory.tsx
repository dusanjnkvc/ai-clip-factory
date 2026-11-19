"use client";



import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";

import { Activity, ArrowDownToLine, ArrowRight, ArrowUpRight, AudioLines, Bell, Check, CheckCheck, ChevronDown, ChevronRight, CircleHelp, Clapperboard, Clock3, Cloud, Coins, Copy, ExternalLink, FileCheck2, FileText, Film, FolderOpen, Gauge, LayoutDashboard, Link2, LoaderCircle, LogOut, Menu, MoreHorizontal, Play, Plus, Radio, RefreshCw, Scissors, Send, Settings2, ShieldCheck, SlidersHorizontal, Sparkles, UploadCloud, Users, Video, WandSparkles, X, Zap } from "lucide-react";



import { api, downloadArtifact } from "@/lib/api";
import LocalCreateFlow from "./local-create-flow";
import ManualRuleFields from "./manual-rule-fields";
import WorkspaceSettings from "./workspace-settings";
import CreativeDirector from "./creative-director";
import AutoCreate from "./auto-create";
import Studio from "./studio";

type Row = Record<string, any>;

type Section = "AUTO CREATE" | "AI Creative Director" | "Dashboard" | "Content Rewards" | "Create Clips" | "Video Library" | "Generated Clips" | "AI Video Editor" | "Publishing Queue" | "Connected Accounts" | "Submissions" | "Earnings & Analytics" | "Settings";

const navigation: { name: Section; icon: typeof LayoutDashboard; group?: string }[] = [

  { name: "Dashboard", icon: LayoutDashboard }, { name: "AUTO CREATE", icon: Zap }, { name: "Content Rewards", icon: FileCheck2 }, { name: "Create Clips", icon: WandSparkles }, { name: "AI Creative Director", icon: Sparkles }, { name: "Video Library", icon: FolderOpen }, { name: "Generated Clips", icon: Film }, { name: "AI Video Editor", icon: Scissors },

  { name: "Publishing Queue", icon: Send, group: "DISTRIBUTE" }, { name: "Connected Accounts", icon: Users }, { name: "Submissions", icon: CheckCheck }, { name: "Earnings & Analytics", icon: Coins }, { name: "Settings", icon: Settings2, group: "WORKSPACE" },

];

const list = (value: any): Row[] => Array.isArray(value) ? value : value?.items || [];

const status = (value: any) => String(value || "pending").replaceAll("_", " ");

const money = (value: any) => value == null ? "—" : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Number(value));

const date = (value: any) => value ? new Date(value).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—";

function Badge({ children, tone = "neutral" }: {children: ReactNode; tone?: string}) { return <span className={`badge ${tone}`}><span />{children}</span>; }

function Empty({ icon: Icon = Film, title, text, action }: {icon?: typeof Film; title: string; text: string; action?: ReactNode}) { return <div className="empty"><div className="empty-icon"><Icon size={25} strokeWidth={1.5} /></div><h3>{title}</h3><p>{text}</p>{action}</div>; }

function Platform({ name }: {name: string}) { return <span className={`platform ${name.toLowerCase()}`}>{name.toLowerCase().includes("youtube") ? "▶" : name.toLowerCase().includes("tiktok") ? "♪" : "◎"}</span>; }



export default function Factory() {

  const [section, setSection] = useState<Section>("Dashboard");

  const [user, setUser] = useState<Row | null>(null);

  const [data, setData] = useState<Row>({ metrics: {}, campaigns: [], clips: [], recent_jobs: [], configuration: {} });

  const [rows, setRows] = useState<Row[]>([]);

  const [sources, setSources] = useState<Row[]>([]);

  const [configuration, setConfiguration] = useState<Row>({});

  const [connected, setConnected] = useState(false);

  const [loading, setLoading] = useState(false);

  const [auth, setAuth] = useState(false);

  const [register, setRegister] = useState(true);

  const [creating, setCreating] = useState(false);

  const [campaignOnly, setCampaignOnly] = useState(false);

  const [selected, setSelected] = useState<Row | null>(null);

  const [toast, setToast] = useState("");

  const [sideOpen, setSideOpen] = useState(false);

  const [notifications, setNotifications] = useState(false);

  const [analytics, setAnalytics] = useState<Row>({});

  const notify = useCallback((text: string) => { setToast(text); }, []);

  useEffect(() => { if (toast) { const timer = setTimeout(() => setToast(""), 6500); return () => clearTimeout(timer); } }, [toast]);

  const refresh = useCallback(async () => {
    try {
      const health = await api("/health");
      if (typeof health.local_no_auth === "boolean") setConfiguration(previous => ({...previous, free_mode:health.free_mode,local_no_auth:health.local_no_auth,browser_mode:health.browser_mode}));
    } catch { /* The actual workspace request supplies its own connection state. */ }
    try {

      const me = await api("/auth/me"); setUser(me); setConnected(true);

      const results = await Promise.allSettled([api("/dashboard"), api("/sources"), api("/settings")]);

      if (results[0].status === "fulfilled") setData(results[0].value);

      if (results[1].status === "fulfilled") setSources(list(results[1].value));

      if (results[2].status === "fulfilled") setConfiguration(results[2].value);

    } catch { setUser(null); }

  }, []);

  const loadSection = useCallback(async () => {

    if (!user) return;

    const endpoints: Partial<Record<Section, string>> = { "Content Rewards": "/campaigns", "Video Library": "/sources", "Generated Clips": "/clips", "AI Video Editor": "/clips", "Publishing Queue": "/publishing", "Connected Accounts": "/accounts", "Submissions": "/submissions" };

    setLoading(true);

    try { if (section === "Earnings & Analytics") setAnalytics(await api("/analytics")); else if (endpoints[section]) setRows(list(await api(endpoints[section]!))); }

    catch (e) { notify((e as Error).message); }

    finally { setLoading(false); }

  }, [section, user?.id, notify]);

  useEffect(() => { refresh(); if(new URLSearchParams(window.location.search).get("view")==="accounts")setSection("Connected Accounts"); }, [refresh]);

  useEffect(() => { setRows([]); loadSection(); }, [loadSection]);

  useEffect(() => { if (!user) return; const timer = setInterval(() => { refresh(); loadSection(); }, 6000); return () => clearInterval(timer); }, [user?.id, refresh, loadSection]); // eslint-disable-line react-hooks/exhaustive-deps

  function go(next: Section) { setSection(next); setSideOpen(false); setSelected(null); }

  function newWork(onlyCampaign = false) { if(!onlyCampaign && freeMode && process.env.NEXT_PUBLIC_BROWSER_MODE!=="true"){go("AUTO CREATE");return;} if (!user && !localNoAuth) { setAuth(true); return; } setCampaignOnly(onlyCampaign); setCreating(true); }

  const metrics = data.metrics || {};

  const campaigns = list(data.campaigns);

  const clips = list(data.clips);

  const jobs = list(data.recent_jobs);

  const config = { ...data.configuration, ...configuration };

  const aiReady = config.ai === true || config.ai?.configured === true;
  const freeMode = config.free_mode !== false;
  const localNoAuth = freeMode && config.local_no_auth !== false;
  const sectionLabel = freeMode && section === "AI Video Editor" ? "Video Editor" : section;

  const [help, setHelp] = useState(false);

  async function openClip(clip: Row) { try { setSelected(await api(`/clips/${clip.id}`)); } catch(e) { notify((e as Error).message); } }



  return <div className="app-shell">

    {sideOpen && <div className="sidebar-backdrop" onClick={() => setSideOpen(false)} />}

    <aside id="workspace-navigation" className={`sidebar ${sideOpen ? "open" : ""}`}>

      <button className="brand" onClick={() => go("Dashboard")}><span className="brand-mark"><Clapperboard size={21} /></span><span>clip<span className="brand-light">factory</span><small>{freeMode ? "FREE LOCAL WORKSPACE" : "AI CREATIVE WORKSPACE"}</small></span></button>

      <button className="workspace-switch" onClick={() => { if (!user && !localNoAuth) setAuth(true); else go("Settings"); }}><span className="workspace-avatar">{user?.name?.[0]?.toUpperCase() || "W"}</span><span>{user?.name ? `${user.name.split(" ")[0]}'s workspace` : "Your workspace"}<small>Personal workspace</small></span><ChevronDown size={14} /></button>

      <nav aria-label="Main navigation">{navigation.filter(item=>item.name!=="AUTO CREATE"||(freeMode&&process.env.NEXT_PUBLIC_BROWSER_MODE!=="true")).map(({ name, icon: Icon, group }) => <div key={name}>{group && <div className="nav-group">{group}</div>}<button aria-current={section === name ? "page" : undefined} className={`nav-item ${section === name ? "active" : ""}`} onClick={() => go(name)}><Icon size={17} strokeWidth={1.7} /><span>{freeMode && name === "AI Video Editor" ? "Video Editor" : name}</span>{name === "Create Clips" && <span className="nav-new">{freeMode ? "LOCAL" : "AI"}</span>}{name === "Publishing Queue" && metrics.scheduled > 0 && <span className="nav-count">{metrics.scheduled}</span>}</button></div>)}</nav>

      <div className="sidebar-bottom"><div className="cloud-note"><span className="cloud-note-icon"><Cloud size={18} /></span><div>{freeMode ? "Runs on your computer" : "Built for the cloud"}<small>{freeMode ? "No paid API calls · CPU rendering" : "No local GPU required"}</small></div><span className="tiny-dot" /></div><button className="help-link" onClick={() => setHelp(true)}><CircleHelp size={16} />Help & getting started<ArrowUpRight size={13} /></button><button className="profile" onClick={() => user || localNoAuth ? go("Settings") : setAuth(true)}><span className="avatar">{user?.name?.[0]?.toUpperCase() || (localNoAuth ? "L" : "Y")}</span><span>{localNoAuth ? "Local workspace" : user?.name || "Your creative workspace"}<small>{localNoAuth ? "Opens directly · saved on this device" : user?.email || "Sign in to get started"}</small></span><MoreHorizontal size={18} /></button></div>

    </aside>



    <div className="main-shell"><header className="topbar"><div className="breadcrumb"><button className="icon-button mobile-menu" aria-label="Open navigation" aria-controls="workspace-navigation" aria-expanded={sideOpen} onClick={() => setSideOpen(true)}><Menu size={20} /></button><span>Workspace</span><ChevronRight size={13} /><strong>{sectionLabel}</strong></div><div className="top-actions"><span className={`connection ${connected ? "online" : ""}`}><span />{connected ? "Workspace connected" : "Local workspace"}</span><div className="notification-wrap"><button className="icon-button" aria-label="Notifications" onClick={() => setNotifications(!notifications)}><Bell size={18} />{jobs.some(j => j.status === "failed") && <i />}</button>{notifications && <div className="notification-popover"><h3>Workspace activity</h3>{jobs.length ? jobs.slice(0, 4).map(j => <p key={j.id}><b>{status(j.status)}</b><br />{j.error || j.stage || "Processing job"}</p>) : <p>You’re all caught up. Processing updates and submission reminders will appear here.</p>}</div>}</div><span className="top-divider" /><button className="avatar small" aria-label={localNoAuth ? "Workspace settings" : user ? "Account settings" : "Sign in"} onClick={() => user || localNoAuth ? go("Settings") : setAuth(true)}>{user?.name?.[0]?.toUpperCase() || (localNoAuth ? "L" : "Y")}</button></div></header>

    <main>

      <div className="page-heading"><div><div className="eyebrow">{section === "Dashboard" ? "YOUR CREATIVE COMMAND CENTER" : "AI CLIP FACTORY"}</div><h1>{section === "Dashboard" ? "Let’s make something worth watching." : sectionLabel}</h1><p>{({ "AUTO CREATE": "Local AI analysis, automatic editing, and one final package.", "Dashboard": "From source video to standout clips. All in one flow.", "Content Rewards": "Campaign rules, creative work, and compliance in one place.", "AI Creative Director": "Measure your footage, compare concepts, and direct every edit locally.", "Create Clips": freeMode ? "Choose your moment. Render it locally. No API key required." : "Find the strongest moments. Give each one its own edit.", "Video Library": "Your authorized source material, ready for its next story.", "Generated Clips": "Distinctive edits. Platform-ready metadata. Full creative control.", "AI Video Editor": "Fine-tune the details and preserve every version.", "Publishing Queue": "Review, authorize, and publish through official integrations.", "Connected Accounts": "Connect your channels. Keep control of every publication.", "Submissions": "Publication is the beginning. Get your campaign submission ready.", "Earnings & Analytics": "Real performance, transparent costs, and verified payouts.", "Settings": freeMode ? "Local processing is enabled. Paid AI calls are blocked." : "Configure your workspace and cloud processing services." } as Record<Section, string>)[section]}</p></div><div className="heading-actions">{section === "Dashboard" && <button className="button secondary" onClick={() => newWork(true)}><Plus size={16} />New campaign</button>}{!["Settings", "Connected Accounts", "Earnings & Analytics", "Submissions", "AI Creative Director"].includes(section) && <button className="button primary" onClick={() => newWork(section === "Content Rewards")}><Zap size={16} fill="currentColor" />{section === "Content Rewards" ? "New campaign" : freeMode ? (process.env.NEXT_PUBLIC_BROWSER_MODE!=="true" ? "AUTO CREATE" : "Create clip") : "Generate FAST"}</button>}</div></div>



      {!user && !localNoAuth && <div className="notice"><ShieldCheck size={18} /><span><strong>Your workspace is ready to set up.</strong> Create a private account to save campaigns, upload videos, and start processing.</span><button onClick={() => setAuth(true)}>Create workspace<ArrowRight size={15} /></button></div>}



      {section === "Dashboard" && <>

        <div className="metric-grid">{[{ title: "Active campaigns", value: metrics.active_campaigns ?? 0, icon: FileCheck2, detail: "Your content opportunities", color: "purple" }, { title: "Clips ready", value: metrics.ready_to_publish ?? 0, icon: Film, detail: "Reviewed and ready to go", color: "mint" }, { title: "Reported views", value: metrics.reported_views?.toLocaleString() ?? "—", icon: Activity, detail: "From connected accounts or imports", color: "blue" }, { title: "Estimated earnings", value: money(metrics.estimated_earnings), icon: Coins, detail: "Estimates · not confirmed payouts", color: "amber" }].map(m => <div className="metric-card" key={m.title}><div><span>{m.title}</span><span className={`metric-icon ${m.color}`}><m.icon size={17} /></span></div><strong>{m.value}</strong><small>{m.detail}</small></div>)}</div>



        <details className="all-metrics"><summary>All workspace metrics<ChevronDown size={13}/></summary><div>{[{label:"Clips generated",value:metrics.clips_generated},{label:"Processing jobs",value:metrics.processing_jobs},{label:"Scheduled videos",value:metrics.scheduled},{label:"Published clips",value:metrics.published},{label:"Pending submissions",value:metrics.pending_submissions},{label:"Approved submissions",value:metrics.approved_submissions},{label:"Rejected submissions",value:metrics.rejected_submissions},{label:"Confirmed earnings",value:money(metrics.confirmed_earnings)},{label:"Actual payouts",value:money(metrics.paid_earnings)},{label:"Processing expenses",value:money(metrics.processing_expenses)}].map(m=><div key={m.label}><span>{m.label}</span><strong>{m.value??0}</strong></div>)}</div></details>

        <section className="creation-banner"><div className="banner-copy"><div className="banner-label"><span className="tiny-dot" />FIRST CLIP FIRST</div><h2>Your best moments.<br /><span>A whole new story.</span></h2><p>{freeMode ? "Choose a moment from your authorized video. Set the crop, add optional subtitles, and render it on your computer." : "Turn an authorized video into distinctive, campaign-ready clips. AI finds the moment. You call the shots."}</p><button className="button light" onClick={() => newWork()}><Zap size={16} fill="currentColor" />{process.env.NEXT_PUBLIC_BROWSER_MODE!=="true" ? "AUTO CREATE" : "Create your first clip"}<ArrowUpRight size={17} /></button><div className="banner-footnote"><ShieldCheck size={12} />Compliance checked before publishing</div></div><div className="flow-art" aria-label="Analyze, edit, and review your clips"><div className="art-glow" /><div className="source-card"><div className="art-card-head"><Video size={13} /><span>YOUR SOURCE</span><span className="tiny-dot" /></div><div className="waveform">{[18,31,23,42,29,55,36,64,44,72,48,36,60,77,51,35,57,43,28,47,24,36,19,30,16].map((h,i) => <span key={i} style={{ height: h }} />)}</div><div className="source-timeline"><span /><span /><span /></div><div className="art-caption">One source. Multiple stories.</div></div><div className="art-connector"><span /><Sparkles size={19} /><span /></div><div className="output-card"><div className="output-preview"><div className="abstract-frame"><span /><span /><span /></div><div className="preview-bars"><span /><span /><span /></div><span className="clip-aspect">9:16</span><div className="art-play"><Play size={16} fill="currentColor" /></div><div className="art-subtitle">THE MOMENT<br /><b>THAT MATTERS.</b></div></div><div className="output-meta"><span className="mini-check"><Check size={10} /></span>Built around your content<Sparkles size={12} /></div></div><div className="floating-pill"><WandSparkles size={14} /><span>{freeMode ? "Your editing choices" : "Unique Edit DNA"}</span><span className="pill-spark">✦</span></div></div></section>



        <div className="workflow-strip">{[{ n: "01", title: "Bring your brief", text: "Campaign rules & source video", icon: FileText }, { n: "02", title: freeMode ? "Choose your moment" : "Let AI find the story", text: freeMode ? "Timing, crop & optional SRT/VTT" : "Distinctive cuts, captions & metadata", icon: Scissors }, { n: "03", title: "Review. Publish. Earn.", text: "Compliance & submissions in sync", icon: Send }].map((s,i) => <div key={s.n}><span className="workflow-number">{s.n}</span><s.icon size={19} /><span><strong>{s.title}</strong><small>{s.text}</small></span>{i < 2 && <ChevronRight className="workflow-chevron" size={16} />}</div>)}</div>



        <div className="dashboard-columns"><section className="panel"><div className="panel-heading"><div><h2>Content Rewards<span className="count-badge">{campaigns.length}</span></h2><p>Campaigns you’re creating for</p></div><button className="text-button" onClick={() => go("Content Rewards")}>View all<ArrowUpRight size={14} /></button></div>{campaigns.length ? <div className="compact-list">{campaigns.slice(0,4).map(c => <button key={c.id} className="campaign-row" onClick={() => { go("Content Rewards"); setSelected(c); }}><span className="campaign-initial"><FileCheck2 size={19} /></span><span><strong>{c.name}</strong><small>{c.rules?.allowed_platforms?.join(" · ") || "Rules need review"}</small></span><Badge tone={c.review_required ? "amber" : "mint"}>{c.review_required ? "Review rules" : status(c.status || "active")}</Badge><ChevronRight size={14} /></button>)}</div> : <Empty icon={FileCheck2} title="Your next opportunity starts here" text="Add a campaign brief. We’ll turn the requirements into your creative checklist." action={<button className="button secondary small-button" onClick={() => newWork(true)}><Plus size={14} />Add your first campaign</button>} />}</section>

        <section className="panel"><div className="panel-heading"><div><h2>Processing activity</h2><p>Your first clip never waits for the batch</p></div><span className="live-label"><span />LIVE</span></div>{jobs.length ? <div className="job-list">{jobs.slice(0,4).map(j => <Job key={j.id} job={j} />)}</div> : <Empty icon={AudioLines} title="Quiet on set. Ready when you are." text="Your analysis, renders, and ready-to-review clips will show up here in real time." action={<button className="text-button" onClick={() => newWork()}>Start a new generation<ArrowRight size={14} /></button>} />}</section></div>

        <section className="panel recent-clips"><div className="panel-heading"><div><h2>Fresh from the factory</h2><p>Your latest generated clips</p></div><button className="text-button" onClick={() => go("Generated Clips")}>View library<ArrowUpRight size={14} /></button></div>{clips.length ? <div className="clip-grid">{clips.slice(0,4).map(c => <ClipCard key={c.id} clip={c} onClick={() => { go("Generated Clips"); void openClip(c); }} />)}</div> : <div className="slim-empty"><Film size={20} /><span>No clips yet. Your first story is one upload away.</span><button className="text-button" onClick={() => newWork()}>Let’s create it<ArrowRight size={14} /></button></div>}</section>

      </>}



      {section === "Create Clips" && <div className="create-page"><section className="panel create-panel"><span className="section-icon"><Scissors size={26} /></span><div className="eyebrow">{freeMode ? "FREE LOCAL PROCESSING" : "MADE FROM YOUR MOMENTS"}</div><h2>Your source. Your moment.</h2><p>{freeMode ? "Pick the source range, choose a crop, and optionally bring an SRT or VTT subtitle file. FFmpeg creates a real vertical MP4 on this computer. No AI subscription or API key is needed." : "Bring a campaign brief and an authorized video. Create an editing plan, synchronized subtitles, and metadata for every platform."}</p><div className="mode-cards"><button onClick={() => newWork()}><FileCheck2 size={23} /><strong>Content Rewards</strong><p>Save the campaign rules, create a clip, and review compliance before publishing.</p><span>{freeMode ? "Create campaign clip" : "Generate FAST"}<ArrowRight size={15} /></span><Badge tone="purple">PRIMARY WORKFLOW</Badge></button><button onClick={() => { if (!user && !localNoAuth) setAuth(true); else { setCampaignOnly(false); setCreating(true); } }}><Scissors size={23} /><strong>{freeMode ? "Local clipping" : "General AI clipping"}</strong><p>{freeMode ? "Manually choose a range from an authorized podcast, interview, or gameplay video." : "Find standalone moments in your authorized source."}</p><span>Create clip<ArrowRight size={15} /></span></button></div><div className="info-line"><ShieldCheck size={15} />{freeMode ? "No paid AI calls. Rendering uses your computer’s CPU." : "Cloud AI + CPU rendering."}</div></section><section className="panel"><div className="panel-heading"><h2>Processing queue</h2><Badge>{jobs.length} jobs</Badge></div>{jobs.length ? jobs.map(j => <Job key={j.id} job={j} />) : <Empty icon={Gauge} title="Ready for your first render" text="Progress is saved, and every completed clip can be previewed and downloaded." />}</section></div>}



      {section === "Content Rewards" && <><div className="filter-bar"><div><FileCheck2 size={16} />All campaigns<span className="count-badge">{rows.length}</span></div><button className="text-button" onClick={loadSection}><RefreshCw size={14} />Refresh</button></div>{loading && !rows.length ? <Loading /> : rows.length ? <div className="campaign-grid">{rows.map(c => <button key={c.id} className="panel campaign-card" onClick={() => setSelected(c)}><div className="campaign-card-top"><span className="campaign-initial"><FileCheck2 size={21} /></span><Badge tone={c.review_required ? "amber" : "mint"}>{c.review_required ? "Review required" : status(c.status || "active")}</Badge></div><h3>{c.name}</h3><p>{c.brief?.slice(0,160)}</p><div className="platform-tags">{(c.rules?.allowed_platforms || []).map((p:string) => <span key={p}><Platform name={p} />{p}</span>)}</div><div className="card-footer"><span>Created {date(c.created_at)}</span><ArrowUpRight size={16} /></div></button>)}</div> : <section className="panel"><Empty icon={FileCheck2} title="Bring the opportunity. We’ll read the fine print." text="Paste a campaign brief, add screenshots or PDFs, and review extracted rules with their source evidence." action={<button className="button primary" onClick={() => newWork(true)}><Plus size={16} />New campaign</button>} /></section>}</>}



      {section === "AI Creative Director" && (process.env.NEXT_PUBLIC_BROWSER_MODE === "true" ? <CreativeDirector notify={notify} onRendered={() => { go("Generated Clips"); void refresh(); }} /> : <section className="panel"><Empty icon={Sparkles} title="Open Creative Director in the browser edition" text="Local footage analysis, editable storyboards, and free rendering run in the GitHub Pages edition. Its workspace is stored in that browser." action={<a className="button primary" href="https://dusanjnkvc.github.io/ai-clip-factory/" target="_blank" rel="noreferrer">Open free browser edition<ExternalLink size={15}/></a>} /></section>)}

      {section === "AUTO CREATE" && <Studio notify={notify}/>}

      {section === "Video Library" && <section className="panel"><div className="panel-heading"><h2>Authorized source videos<span className="count-badge">{rows.length}</span></h2><button className="text-button" onClick={() => newWork()}><UploadCloud size={15} />Upload video</button></div>{rows.length ? <div className="source-list">{rows.map(s => <div className="source-row" key={s.id}><span className="source-icon"><Video size={23} /></span><div><strong>{s.filename || s.name || "Source video"}</strong><small>{s.duration ? `${Math.round(s.duration)} seconds · ` : ""}{s.width && s.height ? `${s.width} × ${s.height} · ` : ""}{date(s.created_at)}</small></div><Badge tone="mint">Rights recorded</Badge><button className="button secondary small-button" onClick={() => newWork()}>Create clips<ArrowRight size={14} /></button></div>)}</div> : <Empty icon={UploadCloud} title="Good stories start with good source material" text="Upload an MP4, MOV, or WebM you own or have permission to use. Originals are preserved." action={<button className="button primary" onClick={() => newWork()}><UploadCloud size={16} />Upload source video</button>} />}</section>}



      {["Generated Clips", "AI Video Editor"].includes(section) && (rows.length ? <div className="clip-grid">{rows.map(c => <ClipCard key={c.id} clip={c} onClick={() => void openClip(c)} />)}</div> : <section className="panel"><Empty icon={section === "AI Video Editor" ? Scissors : Film} title={section === "AI Video Editor" ? "Your edits, down to the frame" : "Your first clip belongs here"} text="Create a clip from an authorized source, then preview, adjust its timing, review compliance, and download the real MP4." action={<button className="button primary" onClick={() => newWork()}><Scissors size={15} />Create a clip</button>} /></section>)}



      {section === "Publishing Queue" && <><div className="notice muted"><ShieldCheck size={18} /><span>Every publication requires explicit authorization and passing blocking checks. Campaigns with manual submissions require you to stay present.</span></div><section className="panel"><div className="panel-heading"><h2>Publishing jobs</h2><button className="text-button" onClick={() => go("Connected Accounts")}>Manage connections<ArrowUpRight size={14} /></button></div>{rows.length ? rows.map(j => <div className="source-row" key={j.id}><Platform name={j.platform || "youtube"} /><div><strong>{j.title || "Clip publication"}</strong><small>{date(j.scheduled_at || j.created_at)}</small>{j.error && <small className="error-text">{j.error}</small>}</div><Badge tone={j.status === "failed" ? "red" : "purple"}>{status(j.status)}</Badge>{["failed","needs_authorization"].includes(j.status)&&<button className="button secondary small-button" onClick={async()=>{try{await api(`/publishing/${j.id}/retry`,{method:"POST"});notify("Presence confirmed. The existing upload will resume.");loadSection();}catch(e){notify((e as Error).message);}}}><RefreshCw size={13}/>{j.status==="needs_authorization"?"I’m here · authorize":"Resume upload"}</button>}</div>) : <Empty icon={Send} title="Every post starts with your approval" text="Open a generated clip to review its compliance checks, connect a channel, and authorize publication. Manual upload packages are also available." action={<button className="button secondary" onClick={() => go("Generated Clips")}>Review your clips<ArrowRight size={15} /></button>} />}</section></>}



      {section === "Connected Accounts" && <div className="accounts-grid">{[{name:"YouTube",key:"youtube",text:"Connect your channel with Google OAuth. Upload approved Shorts through the official YouTube Data API.",label:"Connect YouTube"},{name:"TikTok",key:"tiktok",text:"Manual upload package available. Direct publishing requires an approved Content Posting API integration.",label:"View manual workflow"},{name:"Instagram",key:"instagram",text:"Manual upload package available. Direct publishing requires an eligible account and configured Meta app.",label:"View manual workflow"}].map(p => {const account = rows.find(r => r.platform === p.key && r.status === "connected"); return <section className="panel account-card" key={p.key}><Platform name={p.key} /><h2>{p.name}</h2><Badge tone={account ? "mint" : "neutral"}>{freeMode ? "Manual workflow" : account ? "Connected" : p.key === "youtube" ? "Not connected" : "Manual workflow"}</Badge><p>{freeMode?"Download your MP4 and metadata package, upload through your own account, then record the public URL and actual publication time here.":p.text}</p><button className="button secondary" onClick={async () => { if (!user && !localNoAuth) return setAuth(true); if (freeMode || p.key !== "youtube") { go("Generated Clips"); notify("Open a clip and download its manual publishing package, including MP4 and platform metadata."); return; } try { const result = await api("/accounts/youtube/connect", {method:"POST"}); window.location.href = result.url; } catch(e) { notify((e as Error).message); } }}><Link2 size={15} />{freeMode ? "View manual workflow" : account ? "Reconnect channel" : p.label}<ArrowUpRight size={14} /></button></section>; })}</div>}



      {section === "Submissions" && <section className="panel"><div className="panel-heading"><h2>Campaign submissions</h2><span className="info-line"><Clock3 size={14} />Deadlines start at actual publication</span></div>{rows.length ? rows.map(s => <SubmissionRow key={s.id} submission={s} onUpdate={() => { loadSection(); refresh(); }} notify={notify} />) : <Empty icon={CheckCheck} title="Published is one step. Submitted is another." text="After publication, your post URL and submission instructions appear here with the campaign’s actual deadline. Manual submissions need your confirmation." />}</section>}



      {section === "Earnings & Analytics" && <><Analytics analytics={analytics} onImport={async (file) => { const form = new FormData(); form.append("file", file); await api("/analytics/import-csv", {method:"POST", body:form}); loadSection(); }} notify={notify} /><FinancialRecords notify={notify} onSaved={()=>{loadSection();refresh();}} /></>}



      {section === "Settings" && <WorkspaceSettings localNoAuth={localNoAuth} config={config} freeMode={freeMode} aiReady={aiReady} user={user} refresh={refresh} notify={notify} signIn={()=>setAuth(true)} signOut={async()=>{await api("/auth/logout",{method:"POST"});setUser(null);setData({metrics:{}});notify("Signed out of your workspace.");}}/>}

      <footer className="footer"><span><span className="tiny-dot" />Creative control. Your computer.</span><span>AI Clip Factory<span className="footer-version">v0.1</span></span></footer>

    </main></div>

    {toast && <div className="toast" role="status"><Activity size={17} /><span>{toast}</span><button className="icon-button" aria-label="Dismiss notification" onClick={() => setToast("")}><X size={16} /></button></div>}

    {auth && !localNoAuth && <Modal title={register ? "Create your workspace" : "Welcome back"} subtitle="A private space for your next great clip." close={() => setAuth(false)}><AuthForm register={register} setRegister={setRegister} onSuccess={() => {setAuth(false); refresh();}} /></Modal>}

    {creating && <Modal wide title={campaignOnly ? "New Content Rewards campaign" : "Create something worth watching"} subtitle={campaignOnly ? "Bring the brief. Keep the evidence. Review the rules." : "Your source + your choices → a local render."} close={() => setCreating(false)}><CreateFlow campaignOnly={campaignOnly} campaigns={campaigns} sources={sources} aiReady={aiReady} freeMode={freeMode} onDone={(message) => {setCreating(false); notify(message); refresh(); go(campaignOnly ? "Content Rewards" : "Create Clips");}} /></Modal>}

    {selected && section === "Content Rewards" && <Modal wide title={selected.name} subtitle="Campaign rules and source evidence" close={() => setSelected(null)}><CampaignDetails freeMode={freeMode} campaign={selected} onUpdate={(c) => {setSelected(c); refresh(); loadSection();}} notify={notify} /></Modal>}

    {selected && ["Generated Clips", "AI Video Editor"].includes(section) && <Modal wide title={selected.title || selected.metadata?.youtube?.[0]?.title || "Your generated clip"} subtitle="Preview, compliance, metadata, and editing controls" close={() => setSelected(null)}><ClipDetails freeMode={freeMode} clip={selected} editing={section === "AI Video Editor"} onUpdate={() => {loadSection(); refresh(); if(selected) void openClip(selected);}} notify={notify} /></Modal>}

    {help && <Modal title="From source to first clip" subtitle="A workflow you control." close={() => setHelp(false)}><div className="help-content"><ol><li>{localNoAuth ? "Open the app and start creating. This local workspace has no login or account setup." : "Create your workspace account."}</li><li>Add a campaign brief and review the supplied requirements. Local extraction is a helper, not an AI compliance decision.</li><li>Upload a video you are authorized to use, then choose your clip’s start and end times.</li><li>Optionally upload an SRT or VTT file with subtitle timestamps. Without a subtitle file, the clip is rendered without speech captions.</li><li>Write or edit the title and description, choose the crop, and select Render clip.</li><li>Preview the MP4, review compliance, and download the manual upload package. Record the actual public post URL after publishing.</li></ol><p>{freeMode ? "Free local mode uses FFmpeg on your computer. Paid AI requests are blocked, and automatic transcription or AI moment selection is unavailable. Keep the app open while rendering." : "Hosted processing is available only when explicitly configured. Review the README for configuration."}</p></div></Modal>}

  </div>;

}



function Loading() { return <div className="loading"><LoaderCircle className="spin" size={20} />Loading your workspace…</div>; }

function Job({job}:{job:Row}) {

  const [busy,setBusy]=useState(false);const [error,setError]=useState("");const progress=Number(job.progress||0);

  return <div className="job"><div><span className={`job-icon ${job.status==="failed"?"failed":""}`}>{job.status==="completed"?<Check size={17}/>: ["failed","blocked"].includes(job.status)?<CircleHelp size={17}/>:<LoaderCircle className="spin" size={17}/>}</span><span><strong>{job.campaign_name||`Generation ${String(job.id).slice(0,8)}`}</strong><small>{job.error||job.stage||status(job.status)}</small></span><Badge tone={job.status==="failed"?"red":"purple"}>{status(job.status)}</Badge></div><div className="progress-track"><span style={{width:`${Math.max(0,Math.min(100,progress))}%`}}/></div><small>{Math.round(progress)}%<span>{date(job.created_at)}</span></small>{["failed","blocked"].includes(job.status)&&job.attempts<3&&<button className="text-button retry-job" disabled={busy} onClick={async()=>{setBusy(true);setError("");try{await api(`/jobs/${job.id}/retry`,{method:"POST"});}catch(e){setError((e as Error).message);}finally{setBusy(false);}}}><RefreshCw size={12}/>{busy?"Resuming…":"Retry after resolving the issue"}</button>}{error&&<small className="error-text">{error}</small>}</div>;

}

function ClipCard({clip,onClick}:{clip:Row;onClick:()=>void}) { return <button className="panel clip-card" onClick={onClick}><div className="clip-thumbnail">{clip.preview_url ? <video src={clip.preview_url} preload="metadata" muted playsInline /> : <Film size={32} />}<span className="clip-play"><Play size={20} fill="currentColor" /></span><span className="clip-duration">{Number(clip.media_info?.duration || clip.duration || 0).toFixed(1)}s</span><Badge tone={clip.compliance?.status === "PASS" ? "mint" : "amber"}>{status(clip.compliance?.status || "review required")}</Badge></div><div className="clip-card-info"><h3>{clip.title || clip.metadata?.youtube?.[0]?.title || "Generated clip"}</h3><p>{date(clip.created_at)}<span>9:16 · MP4</span></p></div></button>; }

function Modal({title,subtitle,close,children,wide=false}:{title:string;subtitle?:string;close:()=>void;children:ReactNode;wide?:boolean}) { const ref = useRef<HTMLDivElement>(null); useEffect(() => { const previous = document.activeElement as HTMLElement; const old = document.body.style.overflow; document.body.style.overflow = "hidden"; ref.current?.focus(); const key=(e:KeyboardEvent)=>{if(e.key==="Escape")close();if(e.key==="Tab"){const focusable=ref.current?.querySelectorAll<HTMLElement>('button:not([disabled]),a[href],input:not([disabled]),textarea,select,[tabindex="0"]');if(!focusable?.length)return;const first=focusable[0],last=focusable[focusable.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}}; document.addEventListener("keydown",key); return()=>{document.body.style.overflow=old;document.removeEventListener("keydown",key);previous?.focus();}; }, []); return <div className="modal-backdrop" onClick={e=>{if(e.target===e.currentTarget)close();}}><div className={`modal ${wide?"wide":""}`} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={ref}><div className="modal-heading"><div><h2>{title}</h2>{subtitle&&<p>{subtitle}</p>}</div><button className="icon-button" onClick={close} aria-label="Close dialog"><X size={20}/></button></div>{children}</div></div>; }



function AuthForm({register,setRegister,onSuccess}:{register:boolean;setRegister:(v:boolean)=>void;onSuccess:()=>void}) { const [error,setError]=useState(""); const [busy,setBusy]=useState(false); async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();setBusy(true);setError("");const form=new FormData(e.currentTarget);try{await api(register?"/auth/register":"/auth/login",{method:"POST",body:JSON.stringify(Object.fromEntries(form))});onSuccess();}catch(e){setError((e as Error).message);}finally{setBusy(false);}} return <form className="form-body" onSubmit={submit}>{register&&<label>Your name<input name="name" required placeholder="Alex Morgan" maxLength={100}/></label>}<label>Email address<input name="email" type="email" required autoComplete="email" placeholder="you@example.com"/></label><label>Password<input name="password" type="password" minLength={register?12:1} required autoComplete={register?"new-password":"current-password"} placeholder={register?"At least 12 characters":"Your password"}/></label>{error&&<div className="form-error" role="alert">{error}</div>}<button className="button primary full" disabled={busy}>{busy?<LoaderCircle className="spin" size={16}/>:<ArrowRight size={16}/>} {register?"Create workspace":"Sign in"}</button><button type="button" className="auth-toggle" onClick={()=>setRegister(!register)}>{register?"Already have an account? Sign in":"New here? Create your workspace"}</button></form>; }



function CreateFlow(props:{campaignOnly:boolean;campaigns:Row[];sources:Row[];aiReady:boolean;freeMode:boolean;onDone:(message:string)=>void}) { return props.freeMode ? <LocalCreateFlow {...props}/> : <HostedCreateFlow {...props}/>; }

function HostedCreateFlow({campaignOnly,campaigns,sources,aiReady,onDone}:{campaignOnly:boolean;campaigns:Row[];sources:Row[];aiReady:boolean;onDone:(message:string)=>void}) {

  const [mode,setMode]=useState("fast");const [campaignId,setCampaignId]=useState("");const [general,setGeneral]=useState(false);const [file,setFile]=useState<File|null>(null);const [sourceId,setSourceId]=useState("");const [attachment,setAttachment]=useState<File|null>(null);const [rights,setRights]=useState(false);const [busy,setBusy]=useState(false);const [stage,setStage]=useState("");const [error,setError]=useState("");const [drag,setDrag]=useState(false);

  async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();setBusy(true);setError("");const form=new FormData(e.currentTarget);try{let cid=campaignId;if(!cid){setStage("Saving your campaign brief…");const c=await api("/campaigns",{method:"POST",body:JSON.stringify({name:form.get("name")||"General clipping",brief:form.get("brief")||"General authorized video clipping. No external campaign requirements supplied.",url:form.get("url")||null})});cid=c.id;setCampaignId(cid);if(attachment){setStage("Extracting campaign attachment…");const a=new FormData();a.append("file",attachment);await api(`/campaigns/${cid}/attachments`,{method:"POST",body:a});}}

    if(campaignOnly){onDone("Campaign saved. Review the extracted rules and source evidence before generating.");return;}

    let sid=sourceId;if(!sid){if(!file||!rights)throw new Error("Upload an authorized video and confirm your source rights.");setStage("Uploading and validating source video…");const upload=new FormData();upload.append("file",file);upload.append("rights_confirmed","true");upload.append("rights_note",String(form.get("rights_note")||"I own this source or have explicit permission to edit and republish it."));const source=await api("/sources",{method:"POST",body:upload});sid=source.id;setSourceId(sid);}

    setStage("Adding your generation to the worker queue…");await api("/jobs",{method:"POST",body:JSON.stringify({campaign_id:cid,source_id:sid,mode,clip_count:Number(form.get("clip_count")||1)})});onDone("Generation queued. Each finished clip appears as soon as its compliance check is complete.");

  }catch(e){setError((e as Error).message);}finally{setBusy(false);setStage("");}}

  return <form onSubmit={submit} className="form-body create-form">{!campaignOnly&&<div className="segmented"><button type="button" className={!general?"selected":""} onClick={()=>setGeneral(false)}><FileCheck2 size={15}/>Content Rewards</button><button type="button" className={general?"selected":""} onClick={()=>{setGeneral(true);setCampaignId("");}}><Scissors size={15}/>General clipping</button></div>}

    <div className="form-section-title"><span>01</span>{general?"Your creative brief":"Campaign brief"}<small>Keep the source of every rule</small></div>

    {!campaignOnly&&campaigns.length>0&&!general&&<label>Campaign<select value={campaignId} onChange={e=>setCampaignId(e.target.value)}><option value="">Create a new campaign</option>{campaigns.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>}

    {!campaignId&&<><label>{general?"Project name":"Campaign name"}<input name="name" placeholder={general?"Interview highlights":"Give your campaign a name"} required maxLength={200}/></label>{!general&&<label>Campaign URL <span className="optional">optional · reference only</span><input type="url" name="url" placeholder="https://…"/><small>Paste the requirements below. Private campaign pages are never scraped.</small></label>}<label>{general?"What should we look for?":"Campaign requirements"}<textarea name="brief" rows={5} required={!general} placeholder={general?"Tell us about the audience, tone, and moments you want to highlight…":"Paste the full brief, including permitted platforms, duration, required hashtags, disclosures, rewards, and submission instructions…"}/></label>{!general&&<label className="attachment-input"><FileText size={17}/><span>{attachment?.name||"Add a PDF or campaign screenshot"}<small>Optional · PDF, PNG, JPG</small></span><input type="file" accept="application/pdf,image/png,image/jpeg" onChange={e=>setAttachment(e.target.files?.[0]||null)}/><Plus size={17}/></label>}</>}

    {!campaignOnly&&<><div className="form-section-title"><span>02</span>Authorized source video<small>Your original is preserved</small></div>{sources.length>0&&<label>Source video<select value={sourceId} onChange={e=>setSourceId(e.target.value)}><option value="">Upload a new video</option>{sources.map(s=><option key={s.id} value={s.id}>{s.filename||s.name}</option>)}</select></label>}{!sourceId&&<><label className={`dropzone ${drag?"dragging":""} ${file?"has-file":""}`} onDragOver={e=>{e.preventDefault();setDrag(true);}} onDragLeave={()=>setDrag(false)} onDrop={e=>{e.preventDefault();setDrag(false);setFile(e.dataTransfer.files[0]||null);}}><UploadCloud size={29}/><strong>{file?file.name:"Drop your source video here"}</strong><span>{file?`${(file.size/1024/1024).toFixed(1)} MB · click to replace`:<>or <b>browse files</b> · MP4, MOV, WebM</>}</span><input type="file" accept="video/mp4,video/quicktime,video/webm,video/x-matroska" required={!file} onChange={e=>setFile(e.target.files?.[0]||null)}/></label><label className="checkbox-label"><input type="checkbox" checked={rights} onChange={e=>setRights(e.target.checked)} required/><span>I own this video or have explicit permission to edit and republish it.<small>A public URL alone doesn’t grant usage rights.</small></span></label><label>Rights evidence <span className="optional">optional</span><input name="rights_note" placeholder="License, permission reference, or ownership note"/></label></>}

    <div className="form-section-title"><span>03</span>Your generation settings</div><div className="generation-settings"><label>Processing mode<select value={mode} onChange={e=>setMode(e.target.value)}><option value="fast">⚡ FAST — first clip first</option><option value="quality">✦ QUALITY — deeper analysis</option></select></label><label>Number of clips<select name="clip_count"><option value="1">1 clip</option><option value="3">3 clips</option><option value="5">5 clips</option></select></label></div><div className="info-line"><ShieldCheck size={15}/>Every clip gets its own Edit DNA and compliance checks.</div></>}

    {!aiReady&&<div className="notice warning"><CircleHelp size={17}/><span>Hosted AI needs server configuration. You can save campaign briefs now. Generation requires OPENAI_API_KEY on the API and worker.</span></div>}

    {error&&<div className="form-error" role="alert">{error}</div>}{stage&&<div className="info-line"><LoaderCircle size={15} className="spin"/>{stage}</div>}

    <button className="button primary full" disabled={busy}>{busy?<LoaderCircle size={17} className="spin"/>:campaignOnly?<FileCheck2 size={17}/>:<Zap size={17} fill="currentColor"/>}{busy?"Working…":campaignOnly?"Save & analyze campaign":`Generate ${mode.toUpperCase()}`}<ArrowRight size={16}/></button><p className="form-footnote">Nothing is published automatically. Review your clips and campaign rules first.</p>

  </form>;

}



function CampaignDetails({campaign,onUpdate,notify,freeMode}:{campaign:Row;onUpdate:(c:Row)=>void;notify:(s:string)=>void;freeMode:boolean}) {

  const [rules,setRules]=useState(JSON.stringify(campaign.rules||{},null,2));const [note,setNote]=useState("");const [busy,setBusy]=useState(false);

  useEffect(()=>setRules(JSON.stringify(campaign.rules||{},null,2)),[campaign]);

  return <div className="form-body"><div className="detail-summary"><Badge tone={campaign.review_required?"amber":"mint"}>{campaign.review_required?"Rules need review":"Rules extracted"}</Badge>{campaign.url&&<a href={campaign.url} target="_blank" rel="noreferrer" className="text-button">Original campaign<ExternalLink size={14}/></a>}</div>

    {campaign.analysis_error&&<div className="notice warning"><CircleHelp size={17}/><span>{freeMode && /OPENAI_API_KEY|Cloud AI|hosted AI/i.test(campaign.analysis_error) ? "This brief was saved before free local mode. Extract supplied rules or review them below; no API key is needed." : campaign.analysis_error}</span></div>}

    <label>Original brief<div className="brief-text">{campaign.brief}</div></label>

    {freeMode&&<ManualRuleFields value={rules} onChange={setRules}/>}
    <label>Campaign rules <span className="optional">advanced JSON</span><textarea className="code-input" rows={14} value={rules} onChange={e=>setRules(e.target.value)}/><small>Keep unknown requirements null. Resolve uncertainties only after reviewing the source.</small></label>

    <div className="evidence-box"><h3><FileText size={16}/>Source evidence & uncertainty</h3><pre>{JSON.stringify(campaign.evidence?.length?campaign.evidence:campaign.rules?.evidence||(freeMode?"Review the supplied brief and record the requirements you can verify.":"No extraction evidence is available yet."),null,2)}</pre></div>

    <label>Review evidence<input value={note} onChange={e=>setNote(e.target.value)} placeholder="Describe the source you checked and any rule corrections" minLength={8}/></label>

    <div className="button-row"><button className="button secondary" disabled={busy} onClick={async()=>{setBusy(true);try{const c=await api(`/campaigns/${campaign.id}/analyze`,{method:"POST"});onUpdate(c);notify(c.analysis_error||(freeMode?"Local rule extraction complete. Verify every requirement against the source.":"Campaign analysis complete. Review the evidence and uncertain rules."));}catch(e){notify((e as Error).message);}finally{setBusy(false);}}}>{busy?<LoaderCircle className="spin" size={15}/>:<Sparkles size={15}/>}{freeMode?"Extract supplied rules":"Analyze brief"}</button>

    <button className="button primary" disabled={busy||note.trim().length<8} onClick={async()=>{setBusy(true);try{const parsed=JSON.parse(rules);if(!parsed||typeof parsed!=="object"||Array.isArray(parsed))throw new Error("Rules must be a JSON object.");const c=await api(`/campaigns/${campaign.id}/rules`,{method:"PATCH",body:JSON.stringify({rules:parsed,note})});onUpdate(c);notify("Reviewed campaign rules saved with your evidence note.");}catch(e){notify((e as Error).message);}finally{setBusy(false);}}}><Check size={15}/>Save reviewed rules</button></div>

    {campaign.attachments?.length>0&&<div className="info-line"><FileText size={15}/>{campaign.attachments.map((a:Row)=>a.filename).join(" · ")}</div>}

  </div>;

}



function ClipDetails({clip,editing,onUpdate,notify,freeMode}:{clip:Row;editing:boolean;onUpdate:()=>void;notify:(s:string)=>void;freeMode:boolean}) {

  const [platform,setPlatform]=useState("youtube");const [tab,setTab]=useState(editing?"edit":"metadata");const [busy,setBusy]=useState(false);const [variant,setVariant]=useState(0);

  const metadata=clip.metadata||{};const platformData=metadata[platform]||{};const options=platformData.variants||[];const option=options[variant]||{};const plan=clip.plan||{};

  useEffect(()=>setVariant(metadata[platform]?.recommended_index||0),[platform,clip.id]);

  async function regenerateMetadata(){if(freeMode){notify("Edit the metadata fields directly. Paid AI optimization is disabled in free local mode.");return;}setBusy(true);try{await api(`/clips/${clip.id}/regenerate-metadata`,{method:"POST"});notify("Metadata regenerated and compliance checked.");onUpdate();}catch(e){notify((e as Error).message);}finally{setBusy(false);}}

  async function regenerate(e:FormEvent<HTMLFormElement>){e.preventDefault();setBusy(true);const f=new FormData(e.currentTarget);try{

    const start=Number(f.get("start")),end=Number(f.get("end"));if(end<=start)throw new Error("End time must be after start time.");

    const cropX=Number(f.get("crop_x")),cropY=Number(f.get("crop_y")),zoom=Number(f.get("zoom"));

    let scenes=(plan.scenes||[]).map((s:Row)=>({...s,start:Math.max(s.start,start),end:Math.min(s.end,end),crop_x:cropX,crop_y:cropY,zoom})).filter((s:Row)=>s.end>s.start);

    if(!scenes.length)scenes=[{start,end,crop_x:cropX,crop_y:cropY,zoom,rationale:"User adjusted source selection and crop."}];

    if(start<plan.start||end>plan.end)scenes=[{start,end,crop_x:cropX,crop_y:cropY,zoom,rationale:"User selected a new continuous source range."}];

    const next={...plan,start,end,scenes,hook:f.get("hook"),show_hook:f.get("show_hook")==="on",subtitle_style:f.get("subtitle_style"),subtitles_enabled:f.get("subtitles_enabled")==="on"};

    await api(`/clips/${clip.id}/regenerate`,{method:"POST",body:JSON.stringify({plan:next,optimize_metadata:f.get("optimize_metadata")==="on",mode:"fast"})});

    notify("A new editing version is queued. The original is preserved; follow progress in Create Clips.");onUpdate();

  }catch(e){notify((e as Error).message);}finally{setBusy(false);}}

  return <div className="clip-detail"><div className="clip-preview">{clip.preview_url?<video src={clip.preview_url.startsWith("blob:")?clip.preview_url:`${clip.preview_url}?v=${clip.current_version}`} controls playsInline preload="metadata"/>:<Empty title="Preview unavailable" text="A successful render is needed before a clip can be previewed."/>}<div className="button-row"><button className="button primary" onClick={()=>downloadArtifact(`/clips/${clip.id}/download`).catch((e:Error)=>notify(e.message))}><ArrowDownToLine size={15}/>Download MP4</button><button className="button secondary" onClick={()=>downloadArtifact(`/clips/${clip.id}/package`).catch((e:Error)=>notify(e.message))}><FileText size={15}/>Upload package</button></div><div className="clip-version-label"><Film size={12}/>{clip.media_info?.width} × {clip.media_info?.height} · {Number(clip.media_info?.duration||0).toFixed(1)}s · v{clip.current_version||1}</div></div>

    <div className="clip-inspector"><div className="segmented tabs">{["metadata","compliance","edit","publish"].map(t=><button key={t} className={tab===t?"selected":""} onClick={()=>setTab(t)}>{t[0].toUpperCase()+t.slice(1)}</button>)}</div>

    {tab==="metadata"&&<div className="form-body compact-form"><div className="platform-selector">{["youtube","tiktok","instagram"].map(p=><button key={p} className={platform===p?"selected":""} onClick={()=>setPlatform(p)}><Platform name={p}/>{p==="youtube"?"Shorts":p==="tiktok"?"TikTok":"Reels"}</button>)}</div>

    {options.length>1&&<label>{freeMode?"Metadata version":"Creative alternative"}<select value={variant} onChange={e=>setVariant(Number(e.target.value))}>{options.map((_:Row,i:number)=><option value={i} key={i}>Option {i+1}{i===platformData.recommended_index?(freeMode?" · Selected":" · Recommended"):""}</option>)}</select></label>}

    {Object.keys(option).length?<MetadataEditor key={`${clip.id}-${clip.current_version}-${platform}-${variant}`} clip={clip} freeMode={freeMode} platform={platform} variant={variant} option={option} onUpdate={onUpdate} notify={notify}/>:<p>No metadata available for this platform.</p>}

    {freeMode?<div className="info-line"><ShieldCheck size={14}/>Metadata is editable above. Paid AI optimization is disabled.</div>:<button className="button secondary" disabled={busy} onClick={regenerateMetadata}>{busy?<LoaderCircle className="spin" size={14}/>:<WandSparkles size={14}/>}Optimize titles, captions & hashtags</button>}</div>}

    {tab==="compliance"&&<div className="form-body"><Badge tone={clip.compliance?.status==="PASS"?"mint":"amber"}>{status(clip.compliance?.status||"review required")}</Badge>{(clip.compliance?.checks||[]).map((check:Row,i:number)=><div className="compliance-check" key={i}><ShieldCheck size={16}/><div><strong>{status(check.rule||check.name)}</strong><p>{check.detail||check.message||check.reason}</p></div><Badge tone={check.status==="PASS"?"mint":check.status==="FAIL"?"red":"amber"}>{status(check.status)}</Badge></div>)}

    <ComplianceReview clip={clip} onUpdate={onUpdate} notify={notify}/>

    <div className="evidence-box"><h3>Edit DNA</h3><pre>{JSON.stringify(clip.edit_dna||{},null,2)}</pre></div></div>}

    {tab==="edit"&&<form className="form-body compact-form" onSubmit={regenerate} key={`${clip.id}-${clip.current_version}`}><div className="generation-settings"><label>Source start (seconds)<input name="start" type="number" min="0" step="0.01" defaultValue={plan.start||0} required/></label><label>Source end (seconds)<input name="end" type="number" min="0.1" step="0.01" defaultValue={plan.end||30} required/></label></div><label>Subtitle treatment<select name="subtitle_style" defaultValue={plan.subtitle_style||"clean"}>{["clean","bold","podcast","gaming","karaoke"].map(s=><option key={s}>{s}</option>)}</select></label>

    <label className="checkbox-label"><input type="checkbox" name="subtitles_enabled" defaultChecked={plan.subtitles_enabled!==false}/><span>Show synchronized subtitles</span></label>

    <div className="generation-settings"><label>Horizontal crop (0–1)<input type="number" name="crop_x" min="0" max="1" step="0.05" defaultValue={plan.scenes?.[0]?.crop_x??0.5} required/></label><label>Vertical crop (0–1)<input type="number" name="crop_y" min="0" max="1" step="0.05" defaultValue={plan.scenes?.[0]?.crop_y??0.5} required/></label></div><label>Zoom (1–1.5×)<input type="number" name="zoom" min="1" max="1.5" step="0.05" defaultValue={plan.scenes?.[0]?.zoom??1} required/></label>

    <label>Opening hook<input name="hook" defaultValue={plan.hook||""} maxLength={140}/></label><label className="checkbox-label"><input type="checkbox" name="show_hook" defaultChecked={plan.show_hook}/><span>Show the hook for the opening 2.5 seconds</span></label>{!freeMode&&<label className="checkbox-label"><input type="checkbox" name="optimize_metadata"/><span>Regenerate metadata for this version</span></label>}<p className="info-line"><Film size={15}/>Timing and crop changes create a new render and repeat compliance checks.</p><button className="button primary" disabled={busy}>{busy?<LoaderCircle className="spin" size={15}/>:<RefreshCw size={15}/>}Regenerate video</button><details className="version-history"><summary>Editing versions ({clip.versions?.length||1})</summary>{(clip.versions||[]).map((v:Row)=><p key={v.id}>Version {v.version} · {date(v.created_at)}</p>)}</details></form>}

    {tab==="publish"&&<PublishingForm clip={clip} notify={notify} onUpdate={onUpdate}/>}</div></div>;

}



function MetadataEditor({clip,platform,variant,option,onUpdate,notify,freeMode}:{clip:Row;platform:string;variant:number;option:Row;onUpdate:()=>void;notify:(s:string)=>void;freeMode:boolean}) {

  const [busy,setBusy]=useState(false);

  return <form className="metadata-editor" onSubmit={async(e)=>{e.preventDefault();setBusy(true);const f=new FormData(e.currentTarget);try{const md=structuredClone(clip.metadata);md[platform].variants[variant]={...option,title:String(f.get("title")),description:String(f.get("description")),caption:String(f.get("caption")),hashtags:String(f.get("hashtags")).split(/\s+/).filter(Boolean),opening_hook:String(f.get("opening_hook"))};md[platform].recommended_index=variant;await api(`/clips/${clip.id}/metadata`,{method:"PATCH",body:JSON.stringify({metadata:md})});notify("Metadata saved as a new version. Compliance was rechecked.");onUpdate();}catch(e){notify((e as Error).message);}finally{setBusy(false);}}}>

    {[{key:"title",label:"Title",max:100},{key:"caption",label:"Caption",max:2200},{key:"description",label:"Description",max:5000},{key:"opening_hook",label:"Opening hook",max:250},{key:"hashtags",label:"Hashtags",max:2000}].map(field=><label key={field.key}>{field.label}<textarea name={field.key} rows={field.key==="description"?4:2} defaultValue={Array.isArray(option[field.key])?option[field.key].join(" "):option[field.key]||""} maxLength={field.max} required={field.key==="title"}/></label>)}

    {option.reasoning&&<p className="metadata-reasoning">{option.reasoning}<br/>{freeMode?"User-supplied metadata · no AI score":"Heuristic score: "+option.score+"/100"}</p>}

    <div className="button-row"><button className="button secondary" type="button" onClick={async()=>{await navigator.clipboard.writeText([option.title,option.description,option.caption,(option.hashtags||[]).join(" ")].filter(Boolean).join("\n\n"));notify("Platform metadata copied.");}}><Copy size={13}/>Copy metadata</button><button className="button primary" disabled={busy}><Check size={13}/>{freeMode?"Save metadata":"Save & recommend"}</button></div></form>;

}



function ComplianceReview({clip,onUpdate,notify}:{clip:Row;onUpdate:()=>void;notify:(s:string)=>void}) {

  const [busy,setBusy]=useState(false);const allowed=["branding","content_restrictions","audio_restrictions","source_material","campaign_uncertainties","campaign_contradictions","platforms","approval_requirement","disclosures","campaign_evidence","creative_context","manual_editing","original_footage","music_restrictions","ai_voice_restrictions","paid_promotion","prohibited_footage","audience_restrictions"];

  const checks=(clip.compliance?.checks||[]).filter((c:Row)=>c.status==="REVIEW_REQUIRED"&&allowed.includes(c.rule));

  if(!checks.length&&!clip.compliance?.checks?.some((c:Row)=>c.rule==="draft_approval"&&c.status==="REVIEW_REQUIRED"))return null;

  return <form className="review-form" onSubmit={async(e)=>{e.preventDefault();setBusy(true);const f=new FormData(e.currentTarget);try{const evidence:Row={...clip.compliance?.semantic_evidence};for(const c of checks){const note=String(f.get(c.rule)||"").trim();if(note)evidence[c.rule]={confirmed:true,note};}await api(`/clips/${clip.id}/review`,{method:"POST",body:JSON.stringify({evidence,draft_approved:f.get("draft_approved")==="on",note:f.get("review_note")})});notify("Review evidence saved. Measurable checks remain enforced.");onUpdate();}catch(e){notify((e as Error).message);}finally{setBusy(false);}}}>

    <h3>Record human review</h3><p>Check the actual video and campaign brief. Add evidence for the semantic checks you can confirm.</p>{checks.map((c:Row)=><label key={c.rule}>{status(c.rule)}<textarea name={c.rule} rows={2} placeholder="Evidence you verified (at least 8 characters)" minLength={8}/></label>)}

    <label className="checkbox-label"><input type="checkbox" name="draft_approved" defaultChecked={clip.draft_approved}/><span>Campaign draft approval is confirmed. Include the approval reference in your note.</span></label><label>Review note<input name="review_note" required minLength={8} placeholder="Reviewer evidence and approval reference"/></label><button className="button secondary" disabled={busy}><ShieldCheck size={14}/>Save review evidence</button>

  </form>;

}



function PublishingForm({clip,notify,onUpdate}:{clip:Row;notify:(s:string)=>void;onUpdate:()=>void}) {

  const [manual,setManual]=useState(false);const [authorized,setAuthorized]=useState(false);const [busy,setBusy]=useState(false);const [accounts,setAccounts]=useState<Row[]>([]);

  useEffect(()=>{api("/accounts").then(rows=>setAccounts(list(rows).filter(a=>a.platform==="youtube"&&a.status==="connected"))).catch(()=>{});},[]);

  return <form className="form-body compact-form" onSubmit={async(e)=>{e.preventDefault();setBusy(true);const f=new FormData(e.currentTarget);try{const scheduled=f.get("scheduled_at");await api(manual?`/clips/${clip.id}/record-publication`:`/clips/${clip.id}/publish`,{method:"POST",body:JSON.stringify(manual?{platform:f.get("platform"),url:f.get("url"),published_at:new Date(String(f.get("published_at"))).toISOString(),confirmation:"User confirms this is an actual published post and the actual publication timestamp."}:{account_id:f.get("account_id"),explicit_authorization:authorized,privacy:f.get("privacy"),attended:true,...(scheduled?{scheduled_at:new Date(String(scheduled)).toISOString()}:{})})});notify(manual?"Publication recorded. Open Submissions to prepare the campaign submission.":"Authorized upload queued. Stay present for manual submission and track Publishing Queue.");onUpdate();}catch(e){notify((e as Error).message);}finally{setBusy(false);}}}>

    <div className="segmented"><button type="button" className={!manual?"selected":""} onClick={()=>setManual(false)}>YouTube upload</button><button type="button" className={manual?"selected":""} onClick={()=>setManual(true)}>Record manual post</button></div>

    {manual?<><label>Platform<select name="platform"><option value="youtube">YouTube</option><option value="tiktok">TikTok</option><option value="instagram">Instagram</option></select></label><label>Published post URL<input type="url" name="url" required placeholder="https://…"/></label><label>Actual publication time<input type="datetime-local" name="published_at" required/></label></>:<><p>Upload through your connected YouTube channel. Resolve blocking checks and confirm required draft approvals first.</p>{!accounts.length&&<div className="notice warning"><CircleHelp size={16}/><span>Connect a YouTube channel in Connected Accounts before authorizing an upload.</span></div>}<label>YouTube channel<select name="account_id" required>{!accounts.length&&<option value="">No connected channel</option>}{accounts.map(a=><option key={a.id} value={a.id}>{a.name||a.display_name||a.account_name||a.external_id||"YouTube channel"}</option>)}</select></label><label>Visibility<select name="privacy"><option value="private">Private (review draft)</option><option value="unlisted">Unlisted</option><option value="public">Public</option></select></label><label>Schedule <span className="optional">optional · unavailable for timed manual submissions</span><input type="datetime-local" name="scheduled_at"/></label></>}

    <label className="checkbox-label"><input type="checkbox" checked={authorized} onChange={e=>setAuthorized(e.target.checked)} required/><span>{manual?"I confirm this post is actually published and the timestamp is correct.":"I authorize this upload and will remain available for any manual campaign submission."}</span></label><button className="button primary" disabled={busy||!authorized||!manual&&!accounts.length}>{busy?<LoaderCircle className="spin" size={15}/>:<Send size={15}/>} {manual?"Record publication":"Authorize YouTube upload"}</button>

  </form>;

}



function SubmissionRow({submission:s,onUpdate,notify}:{submission:Row;onUpdate:()=>void;notify:(s:string)=>void}){const remaining=s.deadline?new Date(s.deadline).getTime()-Date.now():null;return <div className="submission-row"><span className="campaign-initial"><CheckCheck size={20}/></span><div><strong>{s.campaign_name||"Campaign submission"}</strong><small>Published {date(s.published_at||s.created_at)}</small>{s.post_url&&<a href={s.post_url} target="_blank" rel="noreferrer" className="text-button">Published post<ExternalLink size={12}/></a>}</div><div className="submission-status"><Badge tone={s.status==="submitted"?"mint":remaining!=null&&remaining<5*60*1000?"red":"amber"}>{status(s.status)}</Badge>{remaining!=null&&!["submitted","approved","rejected"].includes(s.status)&&<small className={remaining<15*60*1000?"error-text":""}>{remaining<=0?"Deadline passed":`${Math.ceil(remaining/60000)} min remaining`}</small>}</div>{(s.submission_url||s.campaign_url)&&<a className="button secondary small-button" href={s.submission_url||s.campaign_url} target="_blank" rel="noreferrer">Open submission<ArrowUpRight size={13}/></a>}{s.status==="pending"&&<button className="button secondary small-button" onClick={async()=>{try{await api(`/submissions/${s.id}/confirm`,{method:"POST",body:JSON.stringify({status:"submitted",confirmation:"User confirms the campaign submission was completed manually."})});notify("Manual submission confirmed and recorded.");onUpdate();}catch(e){notify((e as Error).message);}}}><Check size={13}/>Confirm submitted</button>}</div>;}



function Analytics({analytics,onImport,notify}:{analytics:Row;onImport:(file:File)=>Promise<void>;notify:(s:string)=>void}){const m=analytics.metrics||{};return <><div className="metric-grid">{[{label:"Reported views",value:m.reported_views?.toLocaleString()??"—",detail:"Reported ≠ payment eligible"},{label:"Estimated earnings",value:money(m.estimated_earnings),detail:"Unconfirmed campaign estimates"},{label:"Confirmed earnings",value:money(m.confirmed_earnings),detail:"Confirmed by campaign owner"},{label:"Actual payouts",value:money(m.paid_earnings??m.actual_payouts),detail:"Payments received"}].map(i=><div className="metric-card" key={i.label}><span>{i.label}</span><strong>{i.value}</strong><small>{i.detail}</small></div>)}</div><div className="dashboard-columns"><section className="panel"><div className="panel-heading"><h2>Performance & earnings</h2><label className="button secondary small-button file-button"><UploadCloud size={14}/>Import views CSV<input type="file" accept=".csv,text/csv" onChange={async(e)=>{const file=e.target.files?.[0];if(file)try{await onImport(file);notify("Analytics import saved.");}catch(err){notify((err as Error).message);}}}/></label></div>{list(analytics.earnings).length?<div className="source-list">{list(analytics.earnings).map((e,i)=><div className="source-row" key={e.id||i}><Coins size={19}/><div><strong>{e.campaign_name||e.campaign_id||"Imported earnings"}</strong><small>{status(e.kind||e.status)} · {date(e.created_at)}</small></div><strong>{money(e.amount??e.amount_usd)}</strong></div>)}</div>:<Empty icon={Activity} title="The numbers will tell your story" text="Connect an eligible analytics integration or import a CSV. No views or earnings are estimated without supporting data."/>}</section><section className="panel"><div className="panel-heading"><h2>Processing economics</h2><Gauge size={18}/></div><div className="economics"><label>Processing expenses<strong>{money(m.processing_expenses)}</strong></label><label>Estimated net earnings<strong>{m.estimated_earnings!=null&&m.processing_expenses!=null?money(m.estimated_earnings-m.processing_expenses):"—"}</strong></label><p>Expenses use reported cost records. Provider usage is recorded separately; monetary charges are never guessed.</p><details><summary>CSV import format</summary><p>See README for the exact import columns and supported statuses. Values are validated by the backend before saving.</p></details></div></section></div><section className="panel"><div className="panel-heading"><h2>Published posts</h2></div>{list(analytics.posts).length?list(analytics.posts).map(p=><div className="source-row" key={p.id}><Platform name={p.platform}/><div><strong>{p.title||p.platform}</strong><small>{date(p.published_at)}</small></div><a className="text-button" href={p.url} target="_blank" rel="noreferrer">View post<ExternalLink size={13}/></a></div>):<div className="slim-empty"><Radio size={20}/>Publication results appear here after a real upload or a manual post record.</div>}</section></>;}



function BudgetControls({config,onSaved,notify}:{config:Row;onSaved:()=>void;notify:(s:string)=>void}) {
  const [busy,setBusy]=useState(false);return <form className="budget-controls" onSubmit={async(e)=>{e.preventDefault();setBusy(true);const f=new FormData(e.currentTarget);try{await api("/settings",{method:"PATCH",body:JSON.stringify({monthly_spend_limit_usd:Number(f.get("monthly")),max_job_cost_usd:Number(f.get("job"))})});notify("Workspace spending limits saved.");onSaved();}catch(e){notify((e as Error).message);}finally{setBusy(false);}}}><label>Monthly allowance (USD)<input type="number" name="monthly" min="0" max={config.monthly_spend_limit_usd} step="0.01" defaultValue={config.preferences?.monthly_spend_limit_usd??config.monthly_spend_limit_usd} required/></label><label>Maximum reservation per job (USD)<input type="number" name="job" min="0.01" max={config.max_job_cost_usd} step="0.01" defaultValue={config.preferences?.max_job_cost_usd??config.max_job_cost_usd} required/></label><small>A zero monthly allowance blocks new paid operations. Provider billing limits should also be configured.</small><button className="button secondary" disabled={busy}><Check size={13}/>Save spending limits</button></form>;
}

function FinancialRecords({notify,onSaved}:{notify:(s:string)=>void;onSaved:()=>void}) {
  const [open,setOpen]=useState(false);const [kind,setKind]=useState("earnings");const [campaigns,setCampaigns]=useState<Row[]>([]);const [busy,setBusy]=useState(false);
  useEffect(()=>{if(open)api("/campaigns").then(r=>setCampaigns(list(r))).catch(()=>{});},[open]);
  return <section className="panel financial-records"><div className="panel-heading"><div><h2>Evidence-backed financial records</h2><p>Enter real amounts from campaign reports or provider invoices.</p></div><button className="button secondary small-button" onClick={()=>setOpen(!open)}><Plus size={14}/>{open?"Close form":"Add record"}</button></div>{open&&<form className="form-body financial-form" onSubmit={async(e)=>{e.preventDefault();setBusy(true);const f=new FormData(e.currentTarget);try{await api(kind==="earnings"?"/earnings":"/costs",{method:"POST",body:JSON.stringify(kind==="earnings"?{campaign_id:f.get("campaign_id"),amount:Number(f.get("amount")),currency:f.get("currency"),kind:f.get("earning_kind"),provenance:f.get("provenance")}:{amount:Number(f.get("amount")),provider:f.get("provider")})});notify("Financial record saved. Estimates, confirmed earnings, and payouts remain separate.");setOpen(false);onSaved();}catch(e){notify((e as Error).message);}finally{setBusy(false);}}}><div className="generation-settings"><label>Record type<select value={kind} onChange={e=>setKind(e.target.value)}><option value="earnings">Campaign earnings</option><option value="cost">Processing expense</option></select></label><label>Amount<input type="number" name="amount" min="0" step="0.01" required placeholder="0.00"/></label></div>{kind==="earnings"?<><label>Campaign<select name="campaign_id" required><option value="">Select a campaign</option>{campaigns.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label><div className="generation-settings"><label>Earnings category<select name="earning_kind"><option value="estimated">Estimated earnings</option><option value="confirmed">Confirmed earnings</option><option value="paid">Actual payout received</option></select></label><label>Currency<select name="currency"><option>USD</option><option>EUR</option><option>GBP</option></select></label></div><label>Source evidence<textarea name="provenance" rows={2} required minLength={8} placeholder="Campaign report, payout reference, and reporting period"/></label></>:<label>Provider and invoice reference<input name="provider" required minLength={8} maxLength={100} placeholder="Provider name · invoice reference"/></label>}<p className="form-footnote">Records are additive. Enter each amount once. The dashboard summary includes USD records only; processing expenses use USD.</p><button className="button primary" disabled={busy}><Check size={14}/>Save financial record</button></form>}</section>;
}
