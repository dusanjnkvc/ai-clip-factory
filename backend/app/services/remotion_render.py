"""Render a clean native timeline through the shared Remotion composition."""
import json,secrets,shutil,subprocess,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from .schemas import ClipPlan,Transcript
from .media import timeline_cues,timeline_words,probe_media,sha256_file,run_media,ffmpeg_binary,safe_input_options,PipelineError

def render_remotion(base,plan,transcript,output,assets=None):
    base=Path(base).resolve();output=Path(output).resolve()
    root=Path(__file__).resolve().parents[3];script=root/'frontend/scripts/render-remotion.mjs'
    if not shutil.which('node') or not (root/'frontend/node_modules/@remotion/renderer').is_dir():raise PipelineError('Remotion needs the frontend dependencies. Run npm ci in frontend, then retry. Existing clips are preserved.')
    parsed=ClipPlan.model_validate(plan);speech=Transcript.model_validate(transcript)
    cues=[v.model_dump() for v in parsed.manual_captions] if parsed.manual_captions else timeline_words(parsed,speech) if speech.words else timeline_cues(parsed,speech)
    cues=[{**c,'text':c.get('text',' '+c.get('word',''))} for c in cues]
    if not cues and speech.words:
        words=timeline_words(parsed,speech)
        cues=[{'start':g[0]['start'],'end':g[-1]['end'],'text':' '.join(w['word'] for w in g)} for i in range(0,len(words),5) if (g:=words[i:i+5])]
    if not parsed.subtitles_enabled:cues=[]
    info=probe_media(base);token=secrets.token_urlsafe(32);path=Path(base)
    allowed={token:{'path':str(path),'mime':'video/mp4'}}
    for key,value in (assets or {}).items():allowed[token+'/'+key]=value
    class MediaHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            selected=allowed.get(self.path.lstrip('/'))
            if not selected:self.send_error(404);return
            path=Path(selected['path'])
            size=path.stat().st_size;start=0;end=size-1
            try:
                if self.headers.get('Range'):
                    part=self.headers['Range'].removeprefix('bytes=').split('-');start=int(part[0] or 0);end=min(size-1,int(part[1]) if part[1] else size-1)
                if start<0 or start>end:raise ValueError()
            except (ValueError,IndexError):self.send_error(416);return
            self.send_response(206 if self.headers.get('Range') else 200);self.send_header('Content-Type',selected['mime']);self.send_header('Accept-Ranges','bytes');self.send_header('Access-Control-Allow-Origin','*');self.send_header('Content-Length',str(end-start+1))
            if self.headers.get('Range'):self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
            self.end_headers()
            try:
                with path.open('rb') as stream:
                    stream.seek(start);remaining=end-start+1
                    while remaining:
                        chunk=stream.read(min(1024*1024,remaining))
                        if not chunk:break
                        self.wfile.write(chunk);remaining-=len(chunk)
            except (BrokenPipeError,ConnectionResetError):pass
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),MediaHandler);threading.Thread(target=server.serve_forever,daemon=True).start()
    props={'videoUrl':f'http://127.0.0.1:{server.server_port}/{token}','duration':round(info['duration']*parsed.output_fps),'fps':parsed.output_fps,'width':info['width'],'height':info['height'],'hook':parsed.hook,'showHook':parsed.show_hook,'requiredText':parsed.required_on_video_text,'captions':[{'text':c['text'],'startMs':c['start']*1000,'endMs':c['end']*1000,'timestampMs':None,'confidence':None} for c in cues],'overlays':[v.model_dump() for v in parsed.text_overlays],'captionColor':parsed.caption_color,'captionSize':parsed.caption_size or {'clean':60,'bold':74,'gaming':68,'karaoke':68}.get(parsed.subtitle_style,62),'safeTop':200,'safeBottom':parsed.caption_margin}
    props['editor']=parsed.editor.model_dump() if parsed.editor else None
    props['assets']={key:f'http://127.0.0.1:{server.server_port}/{token}/{key}' for key in (assets or {})}
    if parsed.editor:
        needed={layer.asset_id for layer in parsed.editor.layers if layer.kind!='text'}
        if needed-set(assets or {}):server.shutdown();server.server_close();raise PipelineError('An owned editor asset is missing; render refused.')
    request=Path(output).with_suffix('.remotion.json');request.write_text(json.dumps({'props':props}),encoding='utf-8')
    try:
        result=subprocess.run(['node',str(script),str(request),str(output)],cwd=root/'frontend',capture_output=True,text=True,timeout=max(300,int(info['duration']*40)),encoding='utf-8',errors='replace')
        if result.returncode:raise PipelineError('Remotion rendering failed: '+result.stderr[-1200:])
    finally:server.shutdown();server.server_close();request.unlink(missing_ok=True)
    verified=probe_media(output)
    if verified['codec']!='h264' or not verified['has_audio'] or (verified['width'],verified['height'])!=(info['width'],info['height']) or abs(verified['duration']-info['duration'])>.3:raise PipelineError('Remotion output failed format or timing verification.')
    run_media([ffmpeg_binary(),'-v','error',*safe_input_options(output),'-i',str(output),'-f','null','-'],timeout=max(120,int(info['duration']*5)))
    return {**verified,'sha256':sha256_file(output),'decode_verified':True,'renderer':'remotion','remotion_props':{**{k:v for k,v in props.items() if k!='videoUrl'},'assets':{}}}
