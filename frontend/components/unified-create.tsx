"use client";
import {useEffect,useState} from 'react';
import {api} from '@/lib/api';
import {emptyEditor,newLayer,applyTemplate} from '@/lib/editor-project';
import {prepareEditorImage} from '@/lib/editor-assets';
type Row=Record<string,any>;

export default function UnifiedCreate({onQueued,initialSource=''}:{onQueued:(id:string)=>void;initialSource?:string}){
  const [sources,setSources]=useState<Row[]>([]),[campaigns,setCampaigns]=useState<Row[]>([]);
  const [source,setSource]=useState(initialSource),[file,setFile]=useState<File|null>(null),[brief,setBrief]=useState(''),[document,setDocument]=useState<File|null>(null),[campaign,setCampaign]=useState('');
  const [count,setCount]=useState('3'),[customCount,setCustomCount]=useState(5),[duration,setDuration]=useState('10'),[customDuration,setCustomDuration]=useState(10);
  const [style,setStyle]=useState('opus'),[destination,setDestination]=useState('both'),[rights,setRights]=useState(false),[busy,setBusy]=useState(false),[stage,setStage]=useState(''),[error,setError]=useState('');
  const [url,setUrl]=useState('');
  const [defaults,setDefaults]=useState<Row>({processing_mode:'balanced',output_preset:'portrait_1080',output_fps:30});
  useEffect(()=>{api('/studio/preferences').then(setDefaults).catch(()=>{});},[]);
  const [references,setReferences]=useState<File[]>([]),[templates,setTemplates]=useState<Row[]>([]),[templateId,setTemplateId]=useState(''),[logo,setLogo]=useState<File|null>(null),[username,setUsername]=useState('');
  useEffect(()=>{api('/editor/templates').then(setTemplates).catch(()=>{});},[]);
  useEffect(()=>{Promise.all([api('/sources'),api('/campaigns')]).then(([s,c])=>{setSources(s);setCampaigns(c);}).catch(e=>setError(e.message));},[]);
  useEffect(()=>{const reload=()=>{api('/campaigns').then(setCampaigns).catch(e=>setError(e.message));};window.addEventListener('campaigns-changed',reload);return()=>window.removeEventListener('campaigns-changed',reload);},[]);
  const chosenRules=campaigns.find(c=>c.id===campaign)?.rules;
  const campaignWarnings=chosenRules?[...(chosenRules.uncertainties||[]).length?['Some campaign requirements need review before publication.']:[],...(destination==='both'?['youtube','tiktok']:[destination]).filter(p=>chosenRules.allowed_platforms?.length&&!chosenRules.allowed_platforms.includes(p)||chosenRules.prohibited_platforms?.includes(p)).map(p=>`Campaign rules do not permit ${p}. Publication will be blocked.`)]:[];
  async function generate(){
    setBusy(true);setError('');
    try{
      let sourceId=source;
      if(url.trim()){if(!rights)throw new Error('Confirm permission to download and edit this video.');setStage('Importing authorized recording');sourceId=(await api('/studio/sources/import-url',{method:'POST',body:JSON.stringify({url:url.trim(),rights_confirmed:true})})).id;}
      if(file){if(!rights)throw new Error('Confirm permission to use the uploaded footage.');setStage('Importing your video');const data=new FormData();data.append('file',file);data.append('rights_confirmed','true');data.append('rights_note','I have permission to edit this footage and will review publication rights.');sourceId=(await api('/sources',{method:'POST',body:data})).id;}
      if(!sourceId)throw new Error('Upload a video or choose one from your library.');
      let campaignId=campaign;
      if(brief.trim()||document){setStage('Reading campaign requirements');let c=await api('/campaigns',{method:'POST',body:JSON.stringify({name:document?.name.replace(/\.[^.]+$/,'')||'Video campaign',brief})});campaignId=c.id;
        if(document){const data=new FormData();data.append('file',document);await api(`/campaigns/${c.id}/attachments`,{method:'POST',body:data});}
        c=await api(`/studio/campaigns/${c.id}/analyze`,{method:'POST'});setCampaign(c.id);setCampaigns(old=>[c,...old]);setBrief('');setDocument(null);
      }
      const seconds=duration==='custom'?customDuration:Number(duration);
      const referenceIds:string[]=[];
      for(const reference of references){if(!rights)throw new Error('Confirm rights to the supplied source and reference videos.');setStage('Measuring your reference style');const data=new FormData();data.append('file',reference);data.append('rights_confirmed','true');data.append('rights_note','I have permission to use this reference video for editing guidance.');const s=await api('/sources',{method:'POST',body:data});referenceIds.push((await api('/studio/references',{method:'POST',body:JSON.stringify({source_id:s.id,name:reference.name})})).id);}
      const template=templates.find(t=>t.id===templateId);let design=template?applyTemplate(template.editor,seconds,template.duration):emptyEditor();
      if(logo){setStage('Preparing campaign branding');const form=new FormData();form.set('file',await prepareEditorImage(logo));const asset=await api('/editor/assets',{method:'POST',body:form});design.layers.push({...newLayer('image',seconds,asset.id),name:'Campaign logo',x:.8,y:.02,width:.14,height:.065});}
      if(username.trim())design.layers.push({...newLayer('text',seconds),name:'Streamer username',text:username.trim(),x:.08,y:.04,width:.6,height:.04,font_size:36});
      setStage('Starting gameplay analysis');
      const p=await api('/studio/projects',{method:'POST',body:JSON.stringify({name:file?.name||sources.find(s=>s.id===sourceId)?.filename||'Gaming clips',source_id:sourceId,campaign_id:campaignId||null,reference_ids:referenceIds,editor_template:design,editor_template_duration:seconds,clip_count:count==='custom'?customCount:Number(count),duration:seconds,minimum_duration:Math.max(1,seconds-.5),maximum_duration:Math.min(180,seconds+.5),editing_profile:referenceIds.length?'reference':style,destination,render_engine:'remotion',framing:'fit',...defaults})});
      await api(`/studio/projects/${p.id}/start`,{method:'POST'});onQueued(p.id);
    }catch(e){setError((e as Error).message);}finally{setBusy(false);setStage('');}
  }
  return <section className="panel studio form-body unified-create"><div><h2>Your next gaming Short starts here</h2><p>Upload → Generate → Review → Publish → Track KPIs</p></div>
    {error&&<p className="form-error" role="alert">{error}</p>}
    <fieldset><legend>1 · Source video</legend><label>Upload video<input type="file" accept="video/*,.mkv" onChange={e=>{setFile(e.target.files?.[0]||null);setSource('');setUrl('');}}/></label><label>Or select from Video Library<select value={source} onChange={e=>{setSource(e.target.value);setFile(null);setUrl('');}}><option value="">Choose a video</option>{sources.map(s=><option key={s.id} value={s.id}>{s.filename}</option>)}</select></label>{file&&<label><input type="checkbox" checked={rights} onChange={e=>setRights(e.target.checked)}/> I own this video or have permission to edit it.</label>}</fieldset>
    <details><summary>Or import an authorized YouTube, Twitch or Kick URL</summary><label>Recording URL<input type="url" placeholder="https://www.youtube.com/watch?v=…" value={url} onChange={e=>{setUrl(e.target.value);setSource('');setFile(null);}}/></label><label><input type="checkbox" checked={rights} onChange={e=>setRights(e.target.checked)}/> I have permission to download and edit this video.</label><p>Public single-video or recording URLs only; live channels are not imported. Restricted videos require an authorized local file.</p></details>
    <fieldset><legend>2 · Clip rules · text or PDF</legend><p>Optional. Add the requirements for these clips here.</p><label>Saved campaign<select value={campaign} onChange={e=>setCampaign(e.target.value)}><option value="">No campaign</option>{campaigns.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label><label>Upload rules PDF or text file<input type="file" accept=".pdf,.txt,.docx" onChange={e=>setDocument(e.target.files?.[0]||null)}/></label>{document&&<p>Selected rules: {document.name}</p>}<label>Paste clip rules<textarea rows={5} placeholder={'Required hashtags: #Campaign #Gaming\nRequired mentions: @creator\nRequired on-screen text: Your exact wording'} value={brief} onChange={e=>setBrief(e.target.value)}/></label><p>Mandatory hashtags and @mentions go first in publication text. Required on-screen wording is added to the video.</p>{chosenRules&&<div className="rules-summary"><strong>Rules applied to these clips</strong><p>Hashtags first: {chosenRules.required_hashtags?.join(' ')||'None specified'}</p><p>Mentions first: {chosenRules.required_mentions?.join(' ')||'None specified'}</p><p>Visible in video: {chosenRules.required_on_video_text?.join(' · ')||'None specified'}</p></div>}</fieldset>
    <details><summary>Reference videos, logos and reusable designs (optional)</summary><label>Reference examples · up to 3<input type="file" accept="video/*,.mkv" multiple onChange={e=>setReferences(Array.from(e.target.files||[]).slice(0,3))}/></label><label><input type="checkbox" checked={rights} onChange={e=>setRights(e.target.checked)}/> I have permission to use the selected source and reference videos.</label><label>Reusable campaign design<select value={templateId} onChange={e=>setTemplateId(e.target.value)}><option value="">Default design</option>{templates.map(t=><option key={t.id} value={t.id}>{t.name}</option>)}</select></label><label>Campaign logo<input type="file" accept=".png,.jpg,.jpeg,.webp,.svg" onChange={e=>setLogo(e.target.files?.[0]||null)}/></label><label>Streamer username<input value={username} onChange={e=>setUsername(e.target.value)} maxLength={100} placeholder="Optional @username"/></label></details>
    <div className="creation-options"><label>Number of clips<select value={count} onChange={e=>setCount(e.target.value)}>{['1','2','3','5','custom'].map(v=><option key={v} value={v}>{v==='custom'?'Custom':v}</option>)}</select></label>{count==='custom'&&<label>Custom clips · 1–10<input type="number" min={1} max={10} value={customCount} onChange={e=>setCustomCount(+e.target.value)}/></label>}
    <label>Duration per clip<select value={duration} onChange={e=>setDuration(e.target.value)}>{['10','15','20','30','45','60','custom'].map(v=><option key={v} value={v}>{v==='custom'?'Custom':v+' seconds'}</option>)}</select></label>{duration==='custom'&&<label>Custom seconds<input type="number" min={2} max={180} value={customDuration} onChange={e=>setCustomDuration(+e.target.value)}/></label>}
    <label>Editing style<select value={style} onChange={e=>setStyle(e.target.value)}><option value="opus">Opus-Style Gaming</option><option value="gaming">Dynamic Gaming</option><option value="cinematic">Cinematic Gaming</option><option value="automatic">AI Auto</option></select></label>
    <label>Destination platform<select value={destination} onChange={e=>setDestination(e.target.value)}><option value="both">Both</option><option value="youtube">YouTube Shorts</option><option value="tiktok">TikTok</option></select></label></div>
    {campaignWarnings.map(w=><p key={w} className="form-error" role="status">{w}</p>)}<button className="button primary generate-clips" disabled={busy} onClick={()=>void generate()}>{busy?stage:'Generate Clips'}</button><p>No application watermark. Local AI and rendering. Review before publishing.</p>
  </section>;
}
