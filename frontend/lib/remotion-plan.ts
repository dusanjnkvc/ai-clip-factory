import type {BrowserRow} from './browser-db';
import type {Caption} from '@remotion/captions';
import type {ClipCompositionProps} from '../remotion/ClipComposition';

export function remotionProps(plan:BrowserRow,cues:Record<string,{cues:{start:number;end:number;text:string}[]}>,videoUrl:string,fontUrl:string):ClipCompositionProps{
  const captions:Caption[]=[],overlays:{start:number;end:number;text:string}[]=[];
  let offset=0;
  for(const scene of plan.scenes){
    if(plan.subtitles_enabled&&plan.caption_settings?.enabled!==false)for(const cue of cues[scene.source_id||plan.source_id]?.cues||[]){
      const start=Math.max(cue.start,scene.start),end=Math.min(cue.end,scene.end);
      if(end>start)captions.push({text:cue.text,startMs:(offset+start-scene.start)*1000,endMs:(offset+end-scene.start)*1000,timestampMs:null,confidence:null});
    }
    if(scene.overlay_text)overlays.push({start:offset,end:offset+Math.min(4,scene.end-scene.start),text:scene.overlay_text});
    offset+=scene.end-scene.start;
  }
  return {videoUrl,fontUrl,hook:plan.hook||'',showHook:!!plan.show_hook,requiredText:plan.required_on_video_text||[],captions,overlays:[...overlays,...(plan.text_overlays||[])],captionColor:plan.caption_settings?.color||'#FFFFFF',captionSize:plan.caption_settings?.font_size||62,safeTop:plan.caption_settings?.safe_top||200,safeBottom:plan.caption_settings?.safe_bottom||300};
}
