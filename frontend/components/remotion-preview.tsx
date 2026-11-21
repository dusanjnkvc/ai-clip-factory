"use client";
import {useEffect,useState} from 'react';
import {Player} from '@remotion/player';
import {ClipComposition,type ClipCompositionProps} from '../remotion/ClipComposition';
import {api} from '@/lib/api';
type Row=Record<string,any>;
export default function RemotionPreview({clip,plan}:{clip:Row;plan?:Row}){
  const [props,setProps]=useState<ClipCompositionProps|null>(null);
  useEffect(()=>{api(process.env.NEXT_PUBLIC_BROWSER_MODE==='true'?`/clips/${clip.id}/remotion`:`/studio/drafts/${clip.id}/remotion`).then(r=>{if(r)setProps({...r,fontUrl:new URL(`${process.env.NEXT_PUBLIC_BASE_PATH||''}/ffmpeg/NotoSans.ttf`,location.origin).href});}).catch(()=>{});},[clip.id,clip.current_version]);
  if(!props)return <video src={clip.preview_url} controls playsInline style={{width:'100%',maxHeight:420}}/>;
  const p=plan?{...props,hook:plan.hook,showHook:plan.show_hook,overlays:plan.text_overlays||props.overlays}:props;
  return <div><Player component={ClipComposition} inputProps={p} compositionWidth={clip.media_info.width} compositionHeight={clip.media_info.height} fps={Math.round(clip.media_info.fps||30)} durationInFrames={Math.max(1,Math.round(clip.media_info.duration*(clip.media_info.fps||30)))} controls style={{width:'100%',maxHeight:460}}/><small>Remotion preview · text updates before rendering. Timing changes apply when saved.</small></div>;
}
