/** Real single-thread FFmpeg WebAssembly, loaded only from this site's assets. */
import type { FFmpeg as FFmpegInstance, FFFSType } from "@ffmpeg/ffmpeg";
import type { BrowserRow } from "./browser-db";
import type { CaptionCue } from "./browser-rules";

let instance: Promise<FFmpegInstance> | undefined;
let currentProgress: ((value: number) => void) | undefined;
let expectedSeconds = 1;
const logs: string[] = [];

function asset(name: string): string {
  return new URL(`${process.env.NEXT_PUBLIC_BASE_PATH || ""}/ffmpeg/${name}`, location.origin).href;
}

async function withDeadline<T>(promise: Promise<T>, milliseconds: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout>;
  try {
    return await Promise.race([promise, new Promise<T>((_, reject) => { timer = setTimeout(() => reject(new Error("Browser rendering exceeded its time limit. Try a shorter clip or a smaller source file.")), milliseconds); })]);
  } finally { clearTimeout(timer!); }
}

async function ffmpeg(): Promise<FFmpegInstance> {
  if (!instance) instance = (async () => {
    if (typeof WebAssembly === "undefined" || typeof Worker === "undefined") throw new Error("This browser does not support WebAssembly workers. Use a current desktop browser.");
    // Keep FFmpeg's worker URLs native to the self-hosted ESM package.
    const { FFmpeg } = await import(/* webpackIgnore: true */ asset("index.js")) as { FFmpeg: new () => FFmpegInstance };
    const engine = new FFmpeg();
    engine.on("log", ({ message }) => { logs.push(message); if (logs.length > 50) logs.shift(); });
    engine.on("progress", ({ time }) => currentProgress?.(Math.max(0, Math.min(.98, time / 1000000 / expectedSeconds))));
    try {
      await withDeadline(engine.load({ classWorkerURL: asset("worker.js"), coreURL: asset("ffmpeg-core.js"), wasmURL: asset("ffmpeg-core.wasm") }), 120000);
      const response = await fetch(asset("NotoSans.ttf"), { credentials: "same-origin" });
      if (!response.ok) throw new Error("The local subtitle font could not be loaded.");
      await engine.writeFile("NotoSans.ttf", new Uint8Array(await response.arrayBuffer()));
      return engine;
    } catch (failure) { engine.terminate(); instance = undefined; throw new Error("The browser renderer could not load. Reload the site and try again. " + String(failure)); }
  })();
  return instance;
}

export async function inspectVideo(blob: Blob): Promise<BrowserRow> {
  const url = URL.createObjectURL(blob);
  try {
    return await new Promise((resolve, reject) => {
      const video = document.createElement("video");
      const timer = setTimeout(() => { video.src = ""; reject(new Error("The source video metadata could not be read. Use a playable MP4 or WebM.")); }, 20000);
      video.preload = "metadata"; video.muted = true;
      video.onloadedmetadata = () => {
        clearTimeout(timer);
        const duration = video.duration, width = video.videoWidth, height = video.videoHeight;
        video.src = "";
        if (!Number.isFinite(duration) || duration < 1 || duration > 3600 || width < 16 || height < 16) reject(new Error("Source videos must be playable, between 1 second and 60 minutes, with valid dimensions."));
        else resolve({ duration, width, height, probe_method: "browser_video_metadata" });
      };
      video.onerror = () => { clearTimeout(timer); video.src = ""; reject(new Error("This browser cannot read the source. Use an H.264 MP4 or a supported WebM video.")); };
      video.src = url;
    });
  } finally { URL.revokeObjectURL(url); }
}

export async function verifyBrowserOutput(blob:Blob,expected:BrowserRow):Promise<BrowserRow>{
  const engine=await ffmpeg(),prefix='verify-'+crypto.randomUUID(),name=prefix+'.mp4',json=prefix+'.json';
  try{
    await engine.writeFile(name,new Uint8Array(await blob.arrayBuffer()));
    const measured=await probe(engine,name,['-protocol_whitelist','file,pipe','-f','mov'],json);
    if(measured.codec!=='h264'||!measured.has_audio||measured.width!==expected.width||measured.height!==expected.height||Math.abs(measured.duration-expected.duration)>.3)throw new Error('Remotion output does not match the required format, duration or audio.');
    if(await withDeadline(engine.exec(['-v','error','-protocol_whitelist','file,pipe','-f','mov','-i',name,'-f','null','-'],300000),330000)!==0)throw new Error('Remotion output failed complete decode verification.');
    return {...measured,decode_verified:true,size_bytes:blob.size};
  }finally{for(const file of [name,json])try{await engine.deleteFile(file);}catch{}}
}

function inputOptions(bytes: Uint8Array): string[] {
  const signature = String.fromCharCode(...bytes.slice(4, 8));
  if (["ftyp", "moov", "mdat", "wide", "free", "skip"].includes(signature)) return ["-protocol_whitelist", "file,pipe", "-format_whitelist", "mov", "-f", "mov", "-enable_drefs", "0", "-use_absolute_path", "0"];
  if (bytes[0] === 0x1a && bytes[1] === 0x45 && bytes[2] === 0xdf && bytes[3] === 0xa3) return ["-protocol_whitelist", "file,pipe", "-format_whitelist", "matroska,webm", "-f", "matroska"];
  throw new Error("Upload MP4/MOV or Matroska/WebM media. Playlists and remote media references are not supported.");
}

async function probe(engine: FFmpegInstance, input: string, options: string[], output: string): Promise<BrowserRow> {
  const result = await withDeadline(engine.ffprobe(["-v", "error", ...options, "-show_streams", "-show_format", "-of", "json", "-o", output, input]), 60000);
  // core 0.12.10 leaves ret=-1 after successful ffprobe. The fresh JSON output
  // below must still exist, parse, and contain validated measured streams.
  if (result !== 0 && result !== -1) throw new Error("FFmpeg could not inspect the media stream. " + logs.slice(-7).join(" "));
  const data = await engine.readFile(output, "utf8");
  const json = JSON.parse(String(data)); const video = json.streams?.find((stream: BrowserRow) => stream.codec_type === "video");
  if (!video) throw new Error("The file has no readable video stream.");
  let width = Number(video.width), height = Number(video.height);
  const rotation = Number(video.side_data_list?.find((item: BrowserRow) => item.rotation != null)?.rotation || video.tags?.rotate || 0);
  if (Math.abs(rotation) % 180 === 90) [width, height] = [height, width];
  const duration = Number(json.format?.duration || video.duration);
  if (!Number.isFinite(duration) || duration <= 0 || width < 16 || height < 16) throw new Error("The media has invalid dimensions or duration.");
  return { width, height, duration, codec: video.codec_name, has_audio: json.streams.some((stream: BrowserRow) => stream.codec_type === "audio") };
}

function assTime(seconds: number): string {
  const hundredths = Math.max(0, Math.round(seconds * 100));
  return `${Math.floor(hundredths / 360000)}:${String(Math.floor(hundredths / 6000) % 60).padStart(2, "0")}:${String(Math.floor(hundredths / 100) % 60).padStart(2, "0")}.${String(hundredths % 100).padStart(2, "0")}`;
}
function assText(value: string): string { return value.replace(/\\/g, "\\\\").replace(/{/g, "\\{").replace(/}/g, "\\}").replace(/\r?\n/g, "\\N").replace(/[\x00-\x08\x0b-\x1f]/g, ""); }

type SourceFile = {blob:Blob;cues:CaptionCue[]};
function assColor(value: string): string {
  const hex=/^#[0-9a-f]{6}$/i.test(value)?value.slice(1):'FFFFFF';
  return '&H00'+hex.slice(4,6)+hex.slice(2,4)+hex.slice(0,2);
}
function captionAnimation(kind:string,x:number,y:number):string {
  if(kind==='fade')return '{\\fad(90,90)}';
  if(kind==='pop')return '{\\fscx92\\fscy92\\t(0,110,\\fscx100\\fscy100)}';
  if(kind==='slide')return `{\\move(${x},${y+18},${x},${y},0,130)}`;
  return '';
}
function captionsAss(plan:BrowserRow,defaultCues:CaptionCue[],sources:Record<string,SourceFile>,width:number,height:number):{text:string;count:number} {
  const settings=plan.caption_settings||{};const ratio=width/1080;
  const base=({clean:62,bold:74,podcast:66,gaming:58,karaoke:68} as BrowserRow)[plan.subtitle_style]||62;
  const size=Math.round((settings.font_size||base)*ratio),top=Math.round((settings.safe_top||220)*ratio),bottom=Math.round((settings.safe_bottom||260)*ratio);
  const alignment=settings.position==='upper'?8:settings.position==='center'?5:2;
  const y=alignment===8?top:alignment===5?height/2:height-bottom;
  let text=`[Script Info]\nScriptType: v4.00+\nPlayResX: ${width}\nPlayResY: ${height}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\nStyle: Caption,Noto Sans,${size},${assColor(settings.color||'#FFFFFF')},${assColor(settings.highlight||'#B6A7FA')},&H00101010,&H80000000,${plan.subtitle_style==='clean'?0:-1},0,0,0,100,100,0,0,1,${Math.max(2,Math.round(3*ratio))},1,${alignment},${Math.round(75*ratio)},${Math.round(75*ratio)},${alignment===8?top:bottom},1\nStyle: Hook,Noto Sans,${Math.round(70*ratio)},&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,8,${Math.round(70*ratio)},${Math.round(70*ratio)},${top},1\nStyle: Label,Noto Sans,${Math.round(50*ratio)},&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,8,${Math.round(70*ratio)},${Math.round(70*ratio)},${top},1\n\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n`;
  let offset=0,count=0;
  for(const scene of plan.scenes){
    const cues=sources[scene.source_id||plan.source_id]?.cues||defaultCues;
    if(plan.subtitles_enabled&&settings.enabled!==false)for(const cue of cues){
      const start=Math.max(cue.start,scene.start),end=Math.min(cue.end,scene.end);
      if(end>start){text+=`Dialogue: 0,${assTime(offset+(start-scene.start)/(scene.speed||1))},${assTime(offset+(end-scene.start)/(scene.speed||1))},Caption,,0,0,0,,${captionAnimation(settings.animation||'none',Math.round(width/2),Math.round(y))}${assText(cue.text)}\n`;count++;}
    }
    if(scene.overlay_text){
      const placement=scene.overlay_position==='bottom'?`{\\an2\\pos(${Math.round(width/2)},${height-bottom})}`:'';
      text+=`Dialogue: 1,${assTime(offset)},${assTime(offset+Math.min(scene.end-scene.start,4))},Label,,0,0,0,,${placement}${assText(scene.overlay_text)}\n`;
    }
    offset+=(scene.end-scene.start)/(scene.speed||1)+(scene.freeze||0);
  }
  if(count>3000)throw new Error('Too many overlapping caption cues for one short export. Simplify the supplied subtitle file.');
  if(plan.show_hook&&plan.hook)text+=`Dialogue: 2,0:00:00.00,${assTime(Math.min(2.5,offset))},Hook,,0,0,0,,${assText(plan.hook)}\n`;
  return {text,count};
}
function cropChain(info:BrowserRow,w:number,h:number,scene:BrowserRow):string {
  const cw=Math.max(2,Math.floor(Math.min(info.width,info.height*w/h)/(scene.zoom||1)/2)*2);
  const ch=Math.max(2,Math.min(info.height,Math.floor(cw*h/w/2)*2));
  const x0=Number(scene.crop_x??.5),y0=Number(scene.crop_y??.5),x1=Number(scene.crop_x_end??x0),y1=Number(scene.crop_y_end??y0);
  const duration=(scene.end-scene.start).toFixed(4);
  const x=`'(in_w-out_w)*(${x0}+(${x1-x0})*min(t/${duration},1))'`;
  const y=`'(in_h-out_h)*(${y0}+(${y1-y0})*min(t/${duration},1))'`;
  return `crop=${cw}:${ch}:${x}:${y},scale=${w}:${h}:flags=bilinear,setsar=1`;
}

export async function renderBrowserClip(source:Blob,plan:BrowserRow,cues:CaptionCue[],mode:string,onProgress:(stage:string,percent:number)=>Promise<void>,sourceFiles:Record<string,SourceFile>={}):Promise<{blob:Blob;media_info:BrowserRow}>{
  await onProgress('Loading the local browser FFmpeg engine',5);
  const engine=await ffmpeg(),prefix='job-'+crypto.randomUUID(),files:string[]=[],mounts:string[]=[];
  const output=prefix+'-render.mp4',captionFile=prefix+'-captions.ass',outputProbe=prefix+'-output.json';
  files.push(output,captionFile,outputProbe);logs.length=0;
  const mainId=plan.source_id||'__main__';
  const sources:Record<string,SourceFile>={[mainId]:{blob:source,cues},...sourceFiles};
  const ids=[...new Set<string>([mainId,...plan.scenes.map((scene:BrowserRow)=>scene.source_id||mainId),...plan.scenes.filter((scene:BrowserRow)=>scene.secondary_source_id).map((scene:BrowserRow)=>scene.secondary_source_id)])];
  const width=plan.output_width||1080,height=plan.output_height||1920;
  if(![[1080,1920],[720,1280],[540,960]].some(([w,h])=>w===width&&h===height))throw new Error('Unsupported vertical output dimensions.');
  const inputs:BrowserRow={},inputArgs:string[]=[];
  try{
    if(ids.length>5)throw new Error('One browser export supports up to five authorized source files.');
    if(ids.reduce((sum,id)=>sum+(sources[id]?.blob.size||0),0)>1500*1024*1024)throw new Error('The selected sources exceed the 1,500 MB combined browser-render allowance.');
    for(const [index,id] of ids.entries()){
      if(!sources[id])throw new Error('A storyboard source is missing. Add its authorized footage before rendering.');
      const blob=sources[id].blob,options=inputOptions(new Uint8Array(await blob.slice(0,32).arrayBuffer()));
      let input=`${prefix}-source-${index}`;const probeFile=`${prefix}-probe-${index}.json`;files.push(probeFile);
      if(blob.size>128*1024*1024){
        // WORKERFS reads Blob slices on demand instead of copying gigabytes
        // into JavaScript and then again into FFmpeg's WebAssembly heap.
        const mount=`/${prefix}-mount-${index}`;await engine.createDir(mount);mounts.push(mount);
        if(!await engine.mount('WORKERFS' as FFFSType,{blobs:[{name:'source',data:blob}]},mount))throw new Error('This browser could not open the large source file.');
        input=mount+'/source';
      }else{files.push(input);await engine.writeFile(input,new Uint8Array(await blob.arrayBuffer()));}
      const info=await probe(engine,input,options,probeFile);
      inputs[id]={index,info};inputArgs.push(...options,'-i',input);
    }
    await onProgress('Building the validated source timeline',15);
    const captions=captionsAss(plan,cues,sources,width,height);await engine.writeFile(captionFile,new TextEncoder().encode(captions.text));
    expectedSeconds=plan.scenes.reduce((total:number,scene:BrowserRow)=>total+(scene.end-scene.start)/(scene.speed||1)+(scene.freeze||0),0);
    const graph:string[]=[],concat:string[]=[];
    for(const [index,scene] of plan.scenes.entries()){
      const selected=inputs[scene.source_id||mainId],speed=scene.speed||1,freeze=scene.freeze||0,duration=(scene.end-scene.start)/speed+freeze;
      if(!selected||scene.start<0||scene.end>selected.info.duration+.05)throw new Error('A storyboard scene extends beyond its source video.');
      const raw=`raw${index}`;
      graph.push(`[${selected.index}:v]trim=start=${scene.start.toFixed(4)}:end=${scene.end.toFixed(4)},setpts=(PTS-STARTPTS)/${speed},fps=30${freeze?`,tpad=stop_mode=clone:stop_duration=${freeze}`:''}[${raw}]`);
      let composed=`compose${index}`;
      if(plan.framing==='facecam'){
        const box=plan.facecam,top=Math.round(height*(plan.facecam_height||.28)/2)*2,bottom=height-top;
        const fw=Math.max(2,Math.floor(selected.info.width*box.width/2)*2),fh=Math.max(2,Math.floor(selected.info.height*box.height/2)*2),fx=Math.min(selected.info.width-fw,Math.floor(selected.info.width*box.x)),fy=Math.min(selected.info.height-fh,Math.floor(selected.info.height*box.y));
        graph.push(`[${raw}]split=2[camraw${index}][gameraw${index}]`);
        graph.push(`[camraw${index}]crop=${fw}:${fh}:${fx}:${fy},scale=${width}:${top}:force_original_aspect_ratio=increase,crop=${width}:${top},setsar=1[cam${index}]`);
        graph.push(`[gameraw${index}]scale=${width}:${bottom}:force_original_aspect_ratio=decrease,pad=${width}:${bottom}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[game${index}]`);
        graph.push(`[cam${index}][game${index}]vstack=inputs=2[${composed}]`);
      }else if(scene.composition==='split'){
        const secondary=inputs[scene.secondary_source_id],start=Number(scene.secondary_start||0);
        if(!secondary||start<0||start+duration>secondary.info.duration+.05)throw new Error('Split-screen footage is missing or too short.');
        graph.push(`[${raw}]${cropChain(selected.info,width,height/2,scene)}[top${index}]`);
        graph.push(`[${secondary.index}:v]trim=start=${start.toFixed(4)}:end=${(start+scene.end-scene.start).toFixed(4)},setpts=(PTS-STARTPTS)/${speed},fps=30${freeze?`,tpad=stop_mode=clone:stop_duration=${freeze}`:''},${cropChain(secondary.info,width,height/2,{...scene,crop_x:.5,crop_y:.5,crop_x_end:.5,crop_y_end:.5,zoom:1})}[bottom${index}]`);
        graph.push(`[top${index}][bottom${index}]vstack=inputs=2[${composed}]`);
      }else if(scene.composition==='fit_blur'){
        graph.push(`[${raw}]split=2[bg${index}][fg${index}]`);
        graph.push(`[bg${index}]${cropChain(selected.info,width,height,{...scene,crop_x:.5,crop_y:.5,zoom:1})},boxblur=20:2[blur${index}]`);
        graph.push(`[fg${index}]scale=w='min(iw,${width})':h='min(ih,${height})':force_original_aspect_ratio=decrease:flags=bilinear,setsar=1[fit${index}]`);
        graph.push(`[blur${index}][fit${index}]overlay=(W-w)/2:(H-h)/2[${composed}]`);
      }else graph.push(`[${raw}]${cropChain(selected.info,width,height,scene)}[${composed}]`);
      const polish:string[]=[];
      if(scene.effect==='contrast')polish.push('eq=contrast=1.06:saturation=1.07');
      if(scene.effect==='retro')polish.push('eq=contrast=1.1:saturation=0.72','noise=alls=2:allf=t');
      if(scene.transition==='fade'&&duration>.5){const fade=Math.min(.14,duration/5);polish.push(`fade=t=in:st=0:d=${fade.toFixed(3)}`,`fade=t=out:st=${(duration-fade).toFixed(3)}:d=${fade.toFixed(3)}`);}
      graph.push(`[${composed}]${polish.length?polish.join(','):'null'}[v${index}]`);
      if(selected.info.has_audio&&plan.audio_treatment!=='mute')graph.push(`[${selected.index}:a]atrim=start=${scene.start.toFixed(4)}:end=${scene.end.toFixed(4)},asetpts=PTS-STARTPTS,atempo=${speed},apad=pad_dur=${freeze},atrim=duration=${duration.toFixed(4)},aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a${index}]`);
      else graph.push(`anullsrc=r=48000:cl=stereo:d=${duration.toFixed(4)}[a${index}]`);
      concat.push(`[v${index}][a${index}]`);
    }
    graph.push(concat.join('')+`concat=n=${plan.scenes.length}:v=1:a=1[video][audio]`);
    graph.push(`[video]ass=filename=${captionFile}:fontsdir=.[outv]`);
    graph.push('[audio]loudnorm=I=-16:TP=-1.5:LRA=11[outa]');
    let lastPercent=20;currentProgress=value=>{const percent=20+Math.floor(value*65);if(percent>lastPercent){lastPercent=percent;void onProgress('Encoding the selected storyboard',percent);}};
    await onProgress('Encoding the selected storyboard',20);
    const exit=await withDeadline(engine.exec(['-hide_banner','-v','error',...inputArgs,'-filter_complex_threads','1','-filter_complex',graph.join(';'),'-map','[outv]','-map','[outa]','-c:v','libx264','-preset',mode==='quality'?'fast':'ultrafast','-crf',mode==='quality'?'21':'24','-pix_fmt','yuv420p','-threads','1','-c:a','aac','-b:a','128k','-ar','48000','-movflags','+faststart',output],1200000),1260000);
    currentProgress=undefined;if(exit!==0)throw new Error('FFmpeg could not encode this storyboard. '+logs.slice(-5).join(' '));
    await onProgress('Checking actual dimensions and full playback decode',88);
    const rendered=await probe(engine,output,['-protocol_whitelist','file,pipe','-f','mov'],outputProbe);
    if(rendered.width!==width||rendered.height!==height||rendered.codec!=='h264'||!rendered.has_audio||Math.abs(rendered.duration-expectedSeconds)>.3)throw new Error('The output failed its resolution, duration, codec, or audio validation.');
    const decoded=await withDeadline(engine.exec(['-v','error','-protocol_whitelist','file,pipe','-f','mov','-i',output,'-f','null','-'],300000),330000);
    if(decoded!==0)throw new Error('The rendered storyboard failed its complete playback decode.');
    const encoded=await engine.readFile(output);if(!(encoded instanceof Uint8Array)||encoded.length<1000)throw new Error('FFmpeg returned an incomplete MP4.');
    const blob=new Blob([encoded.slice().buffer as ArrayBuffer],{type:'video/mp4'});
    return {blob,media_info:{...rendered,decode_verified:true,subtitle_synchronized:true,subtitle_timing:captions.count?'cue':'none',subtitle_words:0,subtitle_phrases:captions.count,source_had_audio:inputs[mainId].info.has_audio,source_count:ids.length,size_bytes:blob.size,renderer:'ffmpeg_wasm_single_thread'}};
  }catch(failure){engine.terminate();instance=undefined;throw failure instanceof Error?failure:new Error(String(failure));}
  finally{currentProgress=undefined;if(engine.loaded){for(const mount of mounts){try{await engine.unmount(mount);}catch{}try{await engine.deleteDir(mount);}catch{}}for(const file of files)try{await engine.deleteFile(file);}catch{/* Failed files may not exist. */}}}
}
