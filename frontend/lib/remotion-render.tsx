"use client";
import {canRenderMediaOnWeb,renderMediaOnWeb} from '@remotion/web-renderer';
import {ClipComposition} from '../remotion/ClipComposition';
import type {BrowserRow} from './browser-db';
import {remotionProps} from './remotion-plan';

export async function renderWithRemotion(base:Blob,plan:BrowserRow,sourceFiles:Record<string,{cues:{start:number;end:number;text:string}[]}>,progress:(stage:string,percent:number)=>Promise<void>){
  const width=plan.output_width||1080,height=plan.output_height||1920,fps=30;
  const check=await canRenderMediaOnWeb({width,height,container:'mp4',videoCodec:'h264',audioCodec:'aac'});
  if(!check.canRender)throw new Error('Remotion needs H.264/AAC browser encoding. Use current Chrome or Edge, or choose the FFmpeg compatibility renderer. '+check.issues.map(i=>i.message).join(' '));
  const url=URL.createObjectURL(base);
  const fontUrl=new URL(`${process.env.NEXT_PUBLIC_BASE_PATH||''}/ffmpeg/NotoSans.ttf`,location.origin).href;
  const props=remotionProps(plan,sourceFiles,url,fontUrl);
  if(plan.editor?.layers.some((l:BrowserRow)=>l.kind!=='text')){
    const {getRecord,mediaUrl}=await import('./browser-db');props.assets={};
    for(const layer of plan.editor.layers){if(!layer.asset_id)continue;const asset=await getRecord('editor_assets',layer.asset_id);if(!asset)throw new Error('A required editor asset is missing.');props.assets[layer.asset_id]=await mediaUrl(asset.storage_key);}
  }
  try{
    const result=await renderMediaOnWeb({composition:{id:'ClipFactory',component:ClipComposition,width,height,fps,defaultProps:props,durationInFrames:Math.round(plan.scenes.reduce((n:number,s:BrowserRow)=>n+(s.end-s.start)/(s.speed||1)+(s.freeze||0),0)*fps)},inputProps:props,container:'mp4',videoCodec:'h264',audioCodec:'aac',videoBitrate:'high',audioBitrate:128000,mediaCacheSizeInBytes:128*1024*1024,onProgress:({progress:value})=>{void progress('Remotion is rendering text, captions and campaign wording',65+Math.floor(value*30));}});
    return {blob:await result.getBlob(),props:{...props,videoUrl:'',assets:{}}};
  }finally{URL.revokeObjectURL(url);}
}
