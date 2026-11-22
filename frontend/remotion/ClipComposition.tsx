import React,{useEffect,useState} from 'react';
import {AbsoluteFill,continueRender,delayRender,useCurrentFrame,useVideoConfig} from 'remotion';
import {Video} from '@remotion/media';
import {loadFont} from '@remotion/fonts';
import type {Caption} from '@remotion/captions';
import {BasicCaptions} from './BasicCaptions';
import {EditorLayers} from './EditorLayers';
import type {EditorState} from '../lib/editor-project';

export type TimedText={start:number;end:number;text:string};
export type ClipCompositionProps={videoUrl:string;fontUrl:string;hook:string;showHook:boolean;requiredText:string[];captions:Caption[];overlays:TimedText[];captionColor:string;captionSize:number;safeTop:number;safeBottom:number;editor?:EditorState|null;assets?:Record<string,string>};

export const ClipComposition=({videoUrl,fontUrl,hook,showHook,requiredText,captions,overlays,captionColor,captionSize,safeTop,safeBottom,editor,assets={}}:ClipCompositionProps)=>{
  const {fps,width,height}=useVideoConfig(),frame=useCurrentFrame();
  const [fontHandle]=useState(()=>delayRender('Loading the packaged caption font'));
  useEffect(()=>{loadFont({family:'ClipFactoryCaption',url:fontUrl}).then(()=>continueRender(fontHandle)).catch(()=>continueRender(fontHandle));},[fontUrl,fontHandle]);
  const seconds=frame/fps,ratio=width/1080;
  const extra=overlays.filter(c=>c.start<=seconds&&seconds<c.end).map(c=>c.text).join('\n');
  const required=requiredText.join('\n');
  const textStyle:React.CSSProperties={position:'absolute',left:72*ratio,right:72*ratio,textAlign:'center',whiteSpace:'pre-wrap',overflowWrap:'anywhere',fontFamily:'ClipFactoryCaption,Arial,sans-serif',fontWeight:700,color:'#fff',lineHeight:1.2,textShadow:'0 2px 5px #000',WebkitTextStroke:`${1.2*ratio}px #111`,paintOrder:'stroke fill'};
  return <AbsoluteFill style={{backgroundColor:editor?.background||'#000',fontFamily:'ClipFactoryCaption,Arial,sans-serif'}}>
    {videoUrl&&<Video name="Edited source footage" src={videoUrl} volume={editor?.source_volume??1} premountFor={fps} objectFit="contain" style={{position:'absolute',width,height,rotate:`${editor?.source_rotation||0}deg`,scale:editor?.source_scale??1,translate:`${(editor?.source_x||0)*width}px ${(editor?.source_y||0)*height}px`,filter:`brightness(${editor?.brightness??1}) contrast(${editor?.contrast??1}) saturate(${editor?.saturation??1}) blur(${(editor?.blur||0)*ratio}px)`}}/>}
    {showHook&&hook&&seconds<2.5&&<div style={{...textStyle,top:safeTop*ratio,fontSize:Math.min(72,Math.max(42,720/Math.max(10,hook.length/5)))*ratio}}>{hook}</div>}
    <BasicCaptions captions={captions} appearance={editor?.caption} premountFor={fps} width={width-144*ratio} style={{position:'absolute',left:72*ratio,...(editor?{top:editor.caption.y*height}:{bottom:safeBottom*ratio}),color:captionColor,fontSize:captionSize*ratio}}/>
    {extra&&<div style={{...textStyle,top:height*.42,fontSize:52*ratio}}>{extra}</div>}
    <EditorLayers editor={editor} assets={assets} captions={captions}/>
    {required&&<div data-campaign-required="true" style={{...textStyle,bottom:Math.max(430,safeBottom+150)*ratio,fontSize:(required.length>180?36:required.length>90?44:52)*ratio,backgroundColor:'#000b',padding:16*ratio,borderRadius:8*ratio}}>{required}</div>}
  </AbsoluteFill>;
};
