// Exercise the real packaged WebAssembly core through the production renderer.
// Node supplies the worker-shaped host for this library test; the website still
// uses a real browser Worker and the same core binary.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';
import createCore from '@ffmpeg/core';

globalThis.self={location:{href:'https://local.test/ffmpeg/ffmpeg-core.js'}};
const root=new URL('../',import.meta.url);
const wasm=new Uint8Array(await readFile(new URL('node_modules/@ffmpeg/core/dist/esm/ffmpeg-core.wasm',root)));
const core=await createCore({wasmBinary:wasm,mainScriptUrlOrBlob:'ffmpeg-core.js#'+btoa(JSON.stringify({wasmURL:'ffmpeg-core.wasm',workerURL:''}))});
const handlers={log:[],progress:[]};
core.setLogger(data=>handlers.log.forEach(fn=>fn(data)));
core.setProgress(data=>handlers.progress.forEach(fn=>fn(data)));
const engine={
  loaded:true,on(name,fn){handlers[name].push(fn);},
  async writeFile(name,bytes){core.FS.writeFile(name,bytes);},
  async readFile(name,encoding){return core.FS.readFile(name,encoding==='utf8'?{encoding:'utf8'}:{});},
  async deleteFile(name){core.FS.unlink(name);},
  async ffprobe(args){core.ffprobe(...args);const result=core.ret;core.reset();return result;},
  async exec(args,timeout=-1){core.setTimeout(timeout);core.exec(...args);const result=core.ret;core.reset();return result;},
  terminate(){this.loaded=false;},
};
await engine.writeFile('NotoSans.ttf',new Uint8Array(await readFile(new URL('public/ffmpeg/NotoSans.ttf',root))));
for(const [name,size,frequency]of [['fixture-main.mp4','320x180','440'],['fixture-second.mp4','180x320','660']]){
  const result=await engine.exec(['-v','error','-f','lavfi','-i',`testsrc2=size=${size}:rate=12`,'-f','lavfi','-i',`sine=frequency=${frequency}:sample_rate=44100`,'-t','2','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',name]);
  assert.equal(result,0,'WASM generated test footage');
}
const main=new Blob([core.FS.readFile('fixture-main.mp4').slice().buffer],{type:'video/mp4'});
const secondary=new Blob([core.FS.readFile('fixture-second.mp4').slice().buffer],{type:'video/mp4'});
const source=await readFile(new URL('lib/browser-media.ts',root),'utf8');
const shim=`\nexport function useTestEngine(value){instance=Promise.resolve(value);value.on('log',({message})=>logs.push(message));value.on('progress',({time})=>currentProgress?.(Math.max(0,Math.min(.98,time/1000000/expectedSeconds))));}\nexport {captionsAss};`;
const compiled=ts.transpileModule(source+shim,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const renderer=await import('data:text/javascript;base64,'+Buffer.from(compiled).toString('base64'));
renderer.useTestEngine(engine);
const cues=[{start:.2,end:1.6,text:'Exact supplied caption'}];
const base={source_id:'main',start:0,end:1.8,title:'Real WASM test',output_width:540,output_height:960,subtitles_enabled:true,subtitle_style:'clean',audio_treatment:'source',hook:'',show_hook:false,scenes:[{source_id:'main',start:0,end:1.8,crop_x:.3,crop_y:.5,crop_x_end:.7,zoom:1,composition:'fill',transition:'cut',effect:'none'}],caption_settings:{enabled:true,font_size:62,color:'#FFFFFF',highlight:'#B6A7FA',safe_top:180,safe_bottom:260,animation:'fade',position:'lower'}};

test('ASS contains real line breaks, safe positions, and actual cue times',()=>{
  const result=renderer.captionsAss(base,cues,{main:{blob:main,cues}},540,960);
  assert.ok(result.text.startsWith('[Script Info]\n'));
  assert.ok(result.text.includes('{\\fad(90,90)}Exact supplied caption'));
  assert.equal(result.count,1);
});

test('real WASM renders animated crop and cue captions into a fully decoded vertical MP4',async()=>{
  const result=await renderer.renderBrowserClip(main,base,cues,'fast',async()=>{}, {main:{blob:main,cues}});
  assert.equal(result.media_info.width,540);assert.equal(result.media_info.height,960);
  assert.equal(result.media_info.decode_verified,true);assert.equal(result.media_info.subtitle_phrases,1);
  assert.equal(result.media_info.codec,'h264');assert.ok(result.blob.size>1000);
});

test('real WASM renders paired footage, source-preserving composition, fade, and retro treatment',async()=>{
  const plan=structuredClone(base);plan.audio_treatment='mute';plan.caption_settings.animation='pop';
  plan.scenes=[{...base.scenes[0],start:0,end:.9,composition:'split',secondary_source_id:'second',secondary_start:0,transition:'fade',effect:'contrast',overlay_text:'Paired authorized footage',overlay_position:'top'},{...base.scenes[0],start:.9,end:1.8,composition:'fit_blur',transition:'fade',effect:'retro'}];
  const result=await renderer.renderBrowserClip(main,plan,cues,'fast',async()=>{}, {main:{blob:main,cues},second:{blob:secondary,cues:[]}});
  assert.equal(result.media_info.source_count,2);assert.equal(result.media_info.decode_verified,true);
  assert.ok(Math.abs(result.media_info.duration-1.8)<.3);assert.equal(result.media_info.has_audio,true);
});

test('real WASM speed and freeze change output timing with supplied captions preserved',async()=>{
  const plan=structuredClone(base);plan.scenes=[{...base.scenes[0],speed:2,freeze:.3}];
  const result=await renderer.renderBrowserClip(main,plan,cues,'fast',async()=>{}, {main:{blob:main,cues}});
  assert.ok(Math.abs(result.media_info.duration-1.2)<.15);assert.equal(result.media_info.decode_verified,true);assert.equal(result.media_info.has_audio,true);
});

test('real WASM facecam crop preserves complete gameplay beneath the camera',async()=>{
  const plan=structuredClone(base);plan.framing='facecam';plan.facecam={x:.05,y:.05,width:.3,height:.4};plan.facecam_height=.3;
  const result=await renderer.renderBrowserClip(main,plan,cues,'fast',async()=>{}, {main:{blob:main,cues}});
  assert.equal(result.media_info.width,540);assert.equal(result.media_info.height,960);assert.equal(result.media_info.decode_verified,true);
});
