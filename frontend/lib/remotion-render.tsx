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
  try{
    const result=await renderMediaOnWeb({composition:{id:'ClipFactory',component:ClipComposition,width,height,fps,defaultProps:props,durationInFrames:Math.round(plan.scenes.reduce((n:number,s:BrowserRow)=>n+s.end-s.start,0)*fps)},inputProps:props,container:'mp4',videoCodec:'h264',audioCodec:'aac',videoBitrate:'high',audioBitrate:128000,mediaCacheSizeInBytes:128*1024*1024,onProgress:({progress:value})=>{void progress('Remotion is rendering text, captions and campaign wording',65+Math.floor(value*30));}});
    return {blob:await result.getBlob(),props:{...props,videoUrl:''}};
  }finally{URL.revokeObjectURL(url);}
}
