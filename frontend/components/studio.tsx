"use client";

import {useEffect,useState} from 'react';
import {api,downloadArtifact} from '@/lib/api';
type Row=Record<string,any>;

export default function Studio({notify}:{notify:(text:string)=>void}) {
  const [projects,setProjects]=useState<Row[]>([]),[sources,setSources]=useState<Row[]>([]),[campaigns,setCampaigns]=useState<Row[]>([]),[references,setReferences]=useState<Row[]>([]);
  const [selected,setSelected]=useState<Row|null>(null),[advisor,setAdvisor]=useState<Row>({}),[directory,setDirectory]=useState<Row>({files:[]});
  const [name,setName]=useState('Gaming project'),[source,setSource]=useState(''),[campaign,setCampaign]=useState(''),[reference,setReference]=useState('');
  const [video,setVideo]=useState<File|null>(null),[document,setDocument]=useState<File|null>(null),[referenceVideo,setReferenceVideo]=useState<File|null>(null);
  const [brief,setBrief]=useState(''),[game,setGame]=useState(''),[rights,setRights]=useState(false),[original,setOriginal]=useState(false);
  const [seconds,setSeconds]=useState(10),[count,setCount]=useState(3),[minimum,setMinimum]=useState(6),[maximum,setMaximum]=useState(20);
  const [mode,setMode]=useState('balanced'),[style,setStyle]=useState('automatic'),[framing,setFraming]=useState('fit');
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[stage,setStage]=useState(''),[editing,setEditing]=useState<Row|null>(null);
  async function refresh() {
    const [p,s,c,r,d]=await Promise.all([api('/studio/projects'),api('/sources'),api('/campaigns'),api('/studio/references'),api('/studio/input-directory')]);
    setProjects(p);setSources(s);setCampaigns(c);setReferences(r);setDirectory(d);
  }
  async function open(id:string) {
    setSelected(await api(`/studio/projects/${id}`));
    setAdvisor(await api(`/studio/projects/${id}/advisor`));
  }
  useEffect(()=>{refresh().catch(e=>setError(e.message));},[]);
  useEffect(()=>{
    if(!selected?.job||!['queued','processing'].includes(selected.job.status))return;
    const timer=setInterval(()=>open(selected.id).catch(e=>setError(e.message)),2500);
    return()=>clearInterval(timer);
  },[selected?.id,selected?.job?.status]);
  async function upload(file:File) {
    if(!rights)throw new Error('Confirm your permission to use the selected videos.');
    const form=new FormData();form.append('file',file);form.append('rights_confirmed','true');
    form.append('rights_note',original?'I created this original footage and authorize editing and publication.':'I have permission to edit this footage. I will review publication rights.');
    return api('/sources',{method:'POST',body:form});
  }
  async function create() {
    setBusy(true);setError('');
    try {
      setStage('Importing source and campaign requirements');
      const sourceId=video?(await upload(video)).id:source;
      if(!sourceId)throw new Error('Choose or upload an original video.');
      let campaignId=campaign;
      if(brief.trim()||document) {
        const created=await api('/campaigns',{method:'POST',body:JSON.stringify({name:name+' campaign',brief})});
        campaignId=created.id;
        if(document){const form=new FormData();form.append('file',document);await api(`/campaigns/${campaignId}/attachments`,{method:'POST',body:form});}
      }
      let referenceId=reference;
      if(referenceVideo){setStage('Measuring the reference style');const uploaded=await upload(referenceVideo);referenceId=(await api('/studio/references',{method:'POST',body:JSON.stringify({source_id:uploaded.id,name:referenceVideo.name})})).id;}
      const project=await api('/studio/projects',{method:'POST',body:JSON.stringify({name,source_id:sourceId,campaign_id:campaignId||null,reference_ids:referenceId?[referenceId]:[],clip_count:count,duration:seconds,minimum_duration:minimum,maximum_duration:maximum,game,original_creator_confirmed:original,processing_mode:mode,editing_profile:style,framing})});
      setSelected({...project,drafts:[]});
      setStage('Starting local analysis');
      await api(`/studio/projects/${project.id}/start`,{method:'POST'});
      await refresh();await open(project.id);
      notify('Project queued. Originals are preserved.');
    }catch(e){setError((e as Error).message);}finally{setBusy(false);setStage('');}
  }
  async function importFromDirectory(filename:string) {
    try {if(!rights)throw new Error('Confirm permission before importing.');setBusy(true);const s=await api('/studio/input-directory/import',{method:'POST',body:JSON.stringify({filename,rights_confirmed:true,rights_note:'I have permission to edit this local source and will review publication rights.'})});setSource(s.id);await refresh();}
    catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  const selectedSource=sources.find(s=>s.id===source);
  return <section className="panel" style={{padding:24}}>
    <div className="panel-heading"><div><h2>Local gaming studio</h2><p>Three edited drafts. Your review and approval. No paid AI calls.</p></div></div>
    {error&&<p role="alert" style={{color:'#ffafb8'}}>{error}</p>}
    <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(290px,1fr))',gap:24}}>
      <div><h3>New project</h3><label>Project name<input value={name} onChange={e=>setName(e.target.value)}/></label>
      <label>Original video<select value={source} onChange={e=>setSource(e.target.value)}><option value="">Choose a source</option>{sources.map(s=><option key={s.id} value={s.id}>{s.filename}</option>)}</select></label>
      {selectedSource&&<p>{selectedSource.filename} · {Number(selectedSource.media_info.duration).toFixed(1)}s · {selectedSource.media_info.width} × {selectedSource.media_info.height} · {(selectedSource.size_bytes/1024/1024).toFixed(1)} MB</p>}
      <label>Or upload video<input type="file" accept="video/*,.mkv,.mov" onChange={e=>setVideo(e.target.files?.[0]||null)}/></label>
      <label><input type="checkbox" checked={rights} onChange={e=>setRights(e.target.checked)}/> I own these videos or have permission to use them.</label>
      <label><input type="checkbox" checked={original} onChange={e=>setOriginal(e.target.checked)}/> I am the original creator.</label>
      <details><summary>Import from your configured folder</summary><input value={directory.path||''} onChange={e=>setDirectory({...directory,path:e.target.value})}/><button className="button secondary" onClick={()=>api('/studio/input-directory',{method:'PATCH',body:JSON.stringify({path:directory.path})}).then(setDirectory).catch(e=>setError(e.message))}>Set folder</button>{directory.files?.map((f:Row)=><p key={f.filename}><button className="button secondary" disabled={busy} onClick={()=>void importFromDirectory(f.filename)}>{f.filename}</button></p>)}</details>
      <label>Game or topic<input value={game} onChange={e=>setGame(e.target.value)}/></label></div>
      <div><h3>Campaign rules</h3><label>Existing campaign<select value={campaign} onChange={e=>setCampaign(e.target.value)}><option value="">No external campaign</option>{campaigns.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
      <label>Or paste campaign requirements<textarea rows={5} value={brief} onChange={e=>setBrief(e.target.value)}/></label>
      <label>PDF, TXT or DOCX requirements<input type="file" accept=".pdf,.txt,.docx" onChange={e=>setDocument(e.target.files?.[0]||null)}/></label>
      <p>Mandatory requirements take priority. Extracted rules remain reviewable in Content Rewards.</p>
      <label>Reference style<select value={reference} onChange={e=>setReference(e.target.value)}><option value="">No reference</option>{references.map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select></label>
      <label>Or upload a reference video<input type="file" accept="video/*" onChange={e=>setReferenceVideo(e.target.files?.[0]||null)}/></label><p>Reference footage is measured for style; it is not inserted into your edit.</p></div>
      <div><h3>Video settings</h3><label>Clips<select value={count} onChange={e=>setCount(+e.target.value)}>{[1,2,3].map(n=><option key={n}>{n}</option>)}</select></label>
      <label>Preferred duration<input type="number" min={1} max={180} value={seconds} onChange={e=>setSeconds(+e.target.value)}/></label>
      <label>Minimum duration<input type="number" min={1} max={180} value={minimum} onChange={e=>setMinimum(+e.target.value)}/></label>
      <label>Maximum duration<input type="number" min={1} max={180} value={maximum} onChange={e=>setMaximum(+e.target.value)}/></label>
      <label>Editing profile<select value={style} onChange={e=>setStyle(e.target.value)}><option value="automatic">AI Automatic</option><option value="gaming">Gaming Viral</option><option value="cinematic">Cinematic</option><option value="clean">Clean Professional</option><option value="reference">Match Reference Style</option></select></label>
      <label>Processing mode<select value={mode} onChange={e=>setMode(e.target.value)}><option value="fast">Fast Campaign</option><option value="balanced">Balanced</option><option value="quality">Quality</option></select></label>
      <label>Framing<select value={framing} onChange={e=>setFraming(e.target.value)}><option value="fit">Full-width gameplay on blurred background</option><option value="crop">Vertical crop with adjustable framing</option></select></label>
      <p>1080 × 1920 · H.264/AAC · Duration follows mandatory campaign bounds.</p><button className="button primary" disabled={busy} onClick={()=>void create()}>{busy?stage:'Create local drafts'}</button></div>
    </div>
    <hr/><h3>Projects</h3><div className="button-row">{projects.map(p=><button className="button secondary" key={p.id} onClick={()=>open(p.id).catch(e=>setError(e.message))}>{p.name} · {p.job?.status||'imported'}</button>)}</div>
    {selected&&<div><h2>{selected.name}</h2>{selected.job&&<p role="status">{selected.job.status} · {selected.job.progress}% · {selected.job.error||selected.job.stage}</p>}
      {selected.job&&['queued','processing'].includes(selected.job.status)&&<button className="button secondary" onClick={()=>api(`/auto/jobs/${selected.job.id}/cancel`,{method:'POST'}).then(()=>open(selected.id)).catch(e=>setError(e.message))}>Cancel processing</button>}
      {selected.job?.payload?.auto_result?.shortfall&&<p>{selected.job.payload.auto_result.shortfall}</p>}
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(280px,1fr))',gap:24}}>{selected.drafts?.map((draft:Row)=><article key={draft.id} className="panel" style={{padding:16}}>
        <h3>{draft.title}</h3><p>Version {draft.current_version} · {draft.decision} · {draft.compliance.status}</p>
        <video src={draft.preview_url+`?v=${draft.current_version}`} controls playsInline preload="metadata" style={{width:'100%',maxHeight:420}}/>
        <p>{Number(draft.media_info.duration).toFixed(1)}s · {draft.plan.edit_dna.visual_effects}</p>
        {['youtube','tiktok'].map(platform=>{const score=draft.evaluation?.platforms?.[platform];const block=draft.metadata[platform];const meta=block.variants[block.recommended_index];return <div key={platform}><h4>{platform} {score?`· Viral Potential ${score.score}/100`:''}</h4><p>{meta.title}</p><p>{meta.description}</p><p>{meta.hashtags.join(' ')}</p><button className="button secondary" onClick={()=>navigator.clipboard.writeText([meta.title,meta.description,...meta.hashtags].join('\n')).then(()=>notify('Copied publication text.'))}>Copy {platform} text</button>{score&&<details><summary>Score breakdown · {score.confidence} confidence</summary>{Object.entries(score.components).map(([k,v])=><p key={k}>{k}: {String(v)}</p>)}<p>{score.evidence_mode} · {score.limitation}</p></details>}</div>;})}
        <div className="button-row"><button className="button primary" onClick={()=>setEditing(draft)}>Edit and review</button><button className="button secondary" onClick={()=>downloadArtifact(`/clips/${draft.id}/download`).catch(e=>setError(e.message))}>Download preview</button></div>
        {!!draft.evaluation?.suggestions?.length&&<button className="button secondary" onClick={()=>api(`/studio/drafts/${draft.id}/auto-improve`,{method:'POST'}).then(()=>{notify('New version queued; approval will be required.');return open(selected.id);}).catch(e=>setError(e.message))}>Auto-improve draft</button>}
      </article>)}</div>
      <h3>Publishing advisor</h3><p>Scores are editorial estimates, not promised views. Only compliant drafts are eligible.</p>{['youtube','tiktok'].map(p=><div key={p}><strong>{p}</strong><p>{advisor[p]?.posting_time}</p>{advisor[p]?.order?.map((r:Row,i:number)=><p key={r.clip_id}>{i+1}. {r.title} · {r.score}/100 · {r.eligible?'eligible':'review required'}</p>)}</div>)}
    </div>}
    {editing&&<DraftEditor draft={editing} onClose={()=>setEditing(null)} onSaved={async()=>{if(selected)await open(selected.id);notify('Draft updated. Review the current version before approval.');}}/>}
  </section>;
}

function DraftEditor({draft,onClose,onSaved}:{draft:Row;onClose:()=>void;onSaved:()=>Promise<void>}) {
  const [plan,setPlan]=useState<Row>(structuredClone(draft.plan)),[metadata,setMetadata]=useState<Row>(structuredClone(draft.metadata));
  const [note,setNote]=useState(''),[evidence,setEvidence]=useState<Row>({}),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const [history,setHistory]=useState<Row[]>([]),[future,setFuture]=useState<Row[]>([]);
  function change(next:Row){setHistory(h=>[...h,structuredClone(plan)]);setFuture([]);setPlan(next);}
  async function act(action:()=>Promise<any>){setBusy(true);setError('');try{await action();await onSaved();onClose();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  function patchScene(index:number,key:string,value:any){const scenes=plan.scenes.map((s:Row,i:number)=>i===index?{...s,[key]:value}:s);change({...plan,scenes,start:Math.min(...scenes.map((s:Row)=>s.start)),end:Math.max(...scenes.map((s:Row)=>s.end))});}
  return <div className="modal-backdrop"><div className="modal" style={{maxWidth:960,maxHeight:'90vh',overflowY:'auto',padding:28}}><h2>Edit draft · version {draft.current_version}</h2><button className="button secondary" onClick={onClose}>Close</button>{error&&<p role="alert">{error}</p>}
    <video controls src={draft.preview_url} style={{width:220,maxHeight:390}}/>
    <div className="button-row"><button className="button secondary" disabled={!history.length} onClick={()=>{setFuture(f=>[plan,...f]);setPlan(history[history.length-1]);setHistory(h=>h.slice(0,-1));}}>Undo</button><button className="button secondary" disabled={!future.length} onClick={()=>{setHistory(h=>[...h,plan]);setPlan(future[0]);setFuture(f=>f.slice(1));}}>Redo</button></div>
    <label>On-video hook<input value={plan.hook} onChange={e=>change({...plan,hook:e.target.value})}/></label>
    <label>Framing<select value={plan.framing} onChange={e=>change({...plan,framing:e.target.value})}><option value="fit">Full gameplay</option><option value="crop">Vertical crop</option></select></label>
    <label>Caption style<select value={plan.subtitle_style} onChange={e=>change({...plan,subtitle_style:e.target.value})}>{['clean','bold','gaming','karaoke','podcast'].map(v=><option key={v}>{v}</option>)}</select></label>
    <label><input type="checkbox" checked={plan.subtitles_enabled} onChange={e=>change({...plan,subtitles_enabled:e.target.checked})}/> Show actual timed captions</label>
    <label>Audio<select value={plan.audio_treatment} onChange={e=>change({...plan,audio_treatment:e.target.value})}><option value="source">Original game audio</option><option value="mute">Mute</option></select></label>
    <label>Volume<input type="range" min={0} max={2} step={.05} value={plan.audio_volume??1} onChange={e=>change({...plan,audio_volume:+e.target.value})}/></label>
    <label><input type="checkbox" checked={plan.audio_denoise||false} onChange={e=>change({...plan,audio_denoise:e.target.checked})}/> Reduce source noise</label>
    <h3>Source timeline</h3>{plan.scenes.map((s:Row,i:number)=><fieldset key={i}><legend>Shot {i+1}</legend>{[['start','Start (seconds)'],['end','End (seconds)'],['zoom','Zoom'],['crop_x','Horizontal crop'],['crop_y','Vertical crop']].map(([key,label])=><label key={key}>{label}<input type="number" step={.01} value={s[key]} onChange={e=>patchScene(i,key,+e.target.value)}/></label>)}<label>Effect<select value={s.effect} onChange={e=>patchScene(i,'effect',e.target.value)}>{['none','contrast','retro'].map(v=><option key={v}>{v}</option>)}</select></label><label>Transition<select value={s.transition} onChange={e=>patchScene(i,'transition',e.target.value)}><option>cut</option><option>fade</option></select></label>{plan.scenes.length>1&&<button className="button secondary" onClick={()=>change({...plan,scenes:plan.scenes.filter((_:Row,n:number)=>n!==i)})}>Remove shot</button>}</fieldset>)}
    <button className="button primary" disabled={busy} onClick={()=>void act(()=>api(`/clips/${draft.id}/regenerate`,{method:'POST',body:JSON.stringify({plan})}))}>Render new version</button>
    <h3>Publication text</h3>{['youtube','tiktok'].map(platform=>{const block=metadata[platform],index=block.recommended_index,m=block.variants[index];function update(key:string,value:any){const variants=block.variants.map((v:Row,i:number)=>i===index?{...v,[key]:value}:v);setMetadata({...metadata,[platform]:{...block,variants}});}return <fieldset key={platform}><legend>{platform}</legend>{!!block.title_candidates?.length&&<label>Title alternatives<select value={m.title} onChange={e=>update('title',e.target.value)}>{block.title_candidates.map((t:Row)=><option key={t.title} value={t.title}>{t.title}</option>)}</select></label>}<label>Title<input value={m.title} onChange={e=>update('title',e.target.value)}/></label><label>Description<textarea rows={4} value={m.description} onChange={e=>update('description',e.target.value)}/></label><label>Caption<textarea value={m.caption} onChange={e=>update('caption',e.target.value)}/></label><label>Hashtags · mandatory tags must stay first<input value={m.hashtags.join(' ')} onChange={e=>update('hashtags',e.target.value.split(/\s+/).filter(Boolean))}/></label></fieldset>;})}
    <button className="button secondary" disabled={busy} onClick={()=>void act(()=>api(`/clips/${draft.id}/metadata`,{method:'PATCH',body:JSON.stringify({metadata})}))}>Save publication text as new version</button>
    <h3>Campaign review</h3>{draft.compliance.checks.filter((c:Row)=>c.status!=='PASS').map((c:Row)=><div key={c.rule}><p>{c.status} · {c.detail}</p>{c.status==='REVIEW_REQUIRED'&&<label>Evidence from your actual review<input placeholder="Describe what you verified" value={evidence[c.rule]||''} onChange={e=>setEvidence({...evidence,[c.rule]:e.target.value})}/></label>}</div>)}
    <label>Review note<textarea value={note} onChange={e=>setNote(e.target.value)}/></label>
    <button className="button secondary" disabled={busy} onClick={()=>void act(()=>api(`/clips/${draft.id}/review`,{method:'POST',body:JSON.stringify({note,draft_approved:true,evidence:Object.fromEntries(Object.entries(evidence).filter(([,v])=>String(v).trim().length>=8).map(([k,v])=>[k,{confirmed:true,note:v}]))})}))}>Record campaign review</button>
    <div className="button-row">{['approved','rejected'].map(decision=><button className="button primary" key={decision} disabled={busy} onClick={()=>void act(()=>api(`/studio/drafts/${draft.id}/decision`,{method:'POST',body:JSON.stringify({decision,note,version:draft.current_version})}))}>{decision==='approved'?'Approve this version':'Reject this draft'}</button>)}</div>
    <p>Any material edit creates a new version and requires fresh approval. These controls never publish.</p>
  </div></div>;
}
