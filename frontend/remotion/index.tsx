import React from 'react';
import {Composition,registerRoot,staticFile} from 'remotion';
import {ClipComposition} from './ClipComposition';

const Root=()=> <Composition id="ClipFactory" component={ClipComposition} durationInFrames={90} fps={30} width={1080} height={1920} defaultProps={{videoUrl:'',fontUrl:staticFile('ffmpeg/NotoSans.ttf'),hook:'',showHook:false,requiredText:[],captions:[],overlays:[],captionColor:'#FFFFFF',captionSize:62,safeTop:200,safeBottom:300}} calculateMetadata={({props})=>({durationInFrames:Math.max(1,Math.round((props as typeof props&{duration?:number}).duration||90)),fps:Number((props as Record<string,unknown>).fps)||30,width:Number((props as Record<string,unknown>).width)||1080,height:Number((props as Record<string,unknown>).height)||1920})}/>;
registerRoot(Root);
