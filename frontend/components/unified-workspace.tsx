"use client";
import {useEffect,useState} from 'react';
import {Clapperboard,WandSparkles,Film,FolderOpen,Activity,Settings2,Menu} from 'lucide-react';
import {api} from '@/lib/api';
import UnifiedCreate from './unified-create';
import GeneratedGallery from './generated-gallery';
import {SocialConnections,PerformanceDashboard} from './social-studio';
import WorkspaceSettings from './workspace-settings';
type Row=Record<string,any>;
const navigation=[{name:'Create Clips',icon:WandSparkles},{name:'Generated Clips',icon:Film},{name:'Video Library',icon:FolderOpen},{name:'Analytics',icon:Activity},{name:'Settings',icon:Settings2}];

export default function UnifiedWorkspace(){
  const [section,setSection]=useState('Create Clips'),[project,setProject]=useState(''),[toast,setToast]=useState(''),[menu,setMenu]=useState(false),[config,setConfig]=useState<Row>({}),[sources,setSources]=useState<Row[]>([]),[error,setError]=useState('');
  const [createSource,setCreateSource]=useState('');
  async function refresh(){try{const [c,s]=await Promise.all([api('/settings'),api('/sources')]);setConfig(c);setSources(s);}catch(e){setError((e as Error).message);}}
  useEffect(()=>{refresh();if(new URLSearchParams(location.search).get('view')==='accounts')setSection('Settings');},[]);
  useEffect(()=>{if(toast){const t=setTimeout(()=>setToast(''),6000);return()=>clearTimeout(t);}},[toast]);
  function go(name:string){setSection(name);setMenu(false);if(name==='Video Library')void refresh();}
  return <div className="app-shell unified-workspace">{menu&&<div className="sidebar-backdrop" onClick={()=>setMenu(false)}/>}
    <aside id="workspace-navigation" className={`sidebar ${menu?'open':''}`}><button className="brand" onClick={()=>go('Create Clips')}><span className="brand-mark"><Clapperboard/></span><span>clip<span className="brand-light">factory</span><small>FREE LOCAL WORKSPACE</small></span></button><p className="workflow-caption">Your gameplay. Ready to share.</p><nav aria-label="Main navigation">{navigation.map(({name,icon:Icon})=><button key={name} className={`nav-item ${section===name?'active':''}`} aria-current={section===name?'page':undefined} onClick={()=>go(name)}><Icon size={18}/>{name}</button>)}</nav><div className="sidebar-bottom"><p>No login · No paid AI calls</p><small>Media stays on your computer until you authorize a post.</small></div></aside>
    <div className="main-shell"><header className="topbar"><button className="icon-button mobile-menu" aria-label="Open navigation" onClick={()=>setMenu(true)}><Menu/></button><strong>{section}</strong><span>Upload → Generate → Review → Publish → Track KPIs</span></header><main><div className="page-heading"><div><div className="eyebrow">AI CLIP FACTORY</div><h1>{section}</h1><p>{section==='Create Clips'?'One video. Your strongest moments. AI handles the edit.':section==='Generated Clips'?'Review, optionally edit, and publish your finished clips.':section==='Analytics'?'Real channel performance. Missing data stays unavailable.':section==='Settings'?'Connect accounts and configure your local workspace.':'Your originals, preserved for the next edit.'}</p></div></div>
    {error&&<p role="alert" className="form-error">{error}</p>}
    {section==='Create Clips'&&<UnifiedCreate initialSource={createSource} onQueued={id=>{setProject(id);go('Generated Clips');setToast('Generation started. Finished clips appear here automatically.');}}/>}
    {section==='Generated Clips'&&<GeneratedGallery projectId={project} notify={setToast}/>}
    {section==='Video Library'&&<section className="panel studio form-body"><h2>Original videos</h2><button className="button secondary" onClick={()=>void refresh()}>Refresh library</button>{sources.map(s=><article key={s.id} className="source-row"><div><strong>{s.filename}</strong><small>{Number(s.media_info?.duration||0).toFixed(1)} seconds · {s.media_info?.width} × {s.media_info?.height}</small></div><button className="button secondary" onClick={()=>{setCreateSource(s.id);go('Create Clips');}}>Create clips</button></article>)}{!sources.length&&<p>Upload your first video in Create Clips. Original files are preserved.</p>}</section>}
    {section==='Analytics'&&<PerformanceDashboard notify={setToast}/>}
    {section==='Settings'&&<><SocialConnections notify={setToast}/><WorkspaceSettings config={config} freeMode localNoAuth aiReady user={null} refresh={refresh} notify={setToast} signIn={()=>{}} signOut={async()=>{}}/></>}
    </main></div>{toast&&<div className="toast" role="status">{toast}<button onClick={()=>setToast('')} aria-label="Dismiss notification">×</button></div>}
  </div>;
}
