import {renderBrowserClip,verifyBrowserOutput} from './browser-media';
import type {BrowserRow} from './browser-db';
import type {CaptionCue} from './browser-rules';

export async function renderClipForBrowser(source:Blob,plan:BrowserRow,cues:CaptionCue[],mode:string,progress:(stage:string,percent:number)=>Promise<void>,sources:Record<string,{blob:Blob;cues:CaptionCue[]}>):Promise<{blob:Blob;baseBlob?:Blob;media_info:BrowserRow}>{
  if(plan.render_engine==='ffmpeg'){if(plan.editor)throw new Error('Editable layers require the Remotion renderer.');return renderBrowserClip(source,plan,cues,mode,progress,sources);}
  const clean={...plan,editor:null,subtitles_enabled:false,show_hook:false,required_on_video_text:[],text_overlays:[],scenes:plan.scenes.map((s:BrowserRow)=>({...s,overlay_text:''}))};
  const base=await renderBrowserClip(source,clean,[],mode,(stage,n)=>progress(stage,Math.round(n*.6)),sources);
  const {renderWithRemotion}=await import('./remotion-render');
  const result=await renderWithRemotion(base.blob,plan,sources,progress);
  await progress('Verifying the actual Remotion MP4',97);
  const verified=await verifyBrowserOutput(result.blob,base.media_info);
  return {blob:result.blob,baseBlob:base.blob,media_info:{...base.media_info,...verified,renderer:'remotion_web',remotion_props:result.props,subtitle_synchronized:!!result.props.captions.length,subtitle_phrases:result.props.captions.length,subtitle_timing:result.props.captions.length?'cue':'none'}};
}
