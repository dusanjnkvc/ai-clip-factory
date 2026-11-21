import React,{useEffect,useState} from 'react';
import {AbsoluteFill,continueRender,delayRender,useCurrentFrame,useVideoConfig} from 'remotion';
import {Video} from '@remotion/media';
import {loadFont} from '@remotion/fonts';
import type {Caption} from '@remotion/captions';
import {BasicCaptions} from './BasicCaptions';

export type TimedText={start:number;end:number;text:string};
export type ClipCompositionProps={videoUrl:string;fontUrl:string;hook:string;showHook:boolean;requiredText:string[];captions:Caption[];overlays:TimedText[];captionColor:string;captionSize:number;safeTop:number;safeBottom:number};

export const ClipComposition=({videoUrl,fontUrl,hook,showHook,requiredText,captions,overlays,captionColor,captionSize,safeTop,safeBottom}:ClipCompositionProps)=>{
  const {fps,width,height}=useVideoConfig(),frame=useCurrentFrame();
  const [fontHandle]=useState(()=>delayRender('Loading the packaged caption font'));
  useEffect(()=>{loadFont({family:'ClipFactoryCaption',url:fontUrl}).then(()=>continueRender(fontHandle)).catch(()=>continueRender(fontHandle));},[fontUrl,fontHandle]);
  const seconds=frame/fps,ratio=width/1080;
  const extra=overlays.filter(c=>c.start<=seconds&&seconds<c.end).map(c=>c.text).join('\n');
  const required=requiredText.join('\n');
  const textStyle:React.CSSProperties={position:'absolute',left:72*ratio,right:72*ratio,textAlign:'center',whiteSpace:'pre-wrap',overflowWrap:'anywhere',fontFamily:'ClipFactoryCaption,Arial,sans-serif',fontWeight:700,color:'#fff',lineHeight:1.2,textShadow:'0 2px 5px #000',WebkitTextStroke:`${1.2*ratio}px #111`,paintOrder:'stroke fill'};
  return <AbsoluteFill style={{backgroundColor:'#000',fontFamily:'ClipFactoryCaption,Arial,sans-serif'}}>
    {videoUrl&&<Video name="Edited source footage" src={videoUrl} premountFor={fps} objectFit="contain" style={{position:'absolute',width,height}}/>}
    {showHook&&hook&&seconds<2.5&&<div style={{...textStyle,top:safeTop*ratio,fontSize:Math.min(72,Math.max(42,720/Math.max(10,hook.length/5)))*ratio}}>{hook}</div>}
    {required&&<div data-campaign-required="true" style={{...textStyle,bottom:Math.max(430,safeBottom+150)*ratio,fontSize:(required.length>180?36:required.length>90?44:52)*ratio,backgroundColor:'#000b',padding:16*ratio,borderRadius:8*ratio}}>{required}</div>}
    <BasicCaptions captions={captions} premountFor={fps} width={width-144*ratio} style={{position:'absolute',left:72*ratio,bottom:safeBottom*ratio,color:captionColor,fontSize:captionSize*ratio}}/>
    {extra&&<div style={{...textStyle,top:height*.42,fontSize:52*ratio}}>{extra}</div>}
  </AbsoluteFill>;
};
