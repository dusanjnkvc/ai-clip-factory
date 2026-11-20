"""Bounded, rebuildable local preview; the imported original is read only."""
from pathlib import Path
import os,tempfile,threading
from .media import run_media,ffmpeg_binary,safe_input_options,probe_media

_lock=threading.Lock()


def build_preview(source,target):
    target=Path(target);source=Path(source)
    if target.resolve()==source.resolve():raise ValueError('Preview cannot overwrite its source.')
    with _lock:
        if target.is_file():return probe_media(target)
        target.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='acf-proxy-',dir=target.parent) as temp:
            output=Path(temp)/'preview.mp4'
            run_media([ffmpeg_binary(),'-v','error','-y',*safe_input_options(source),'-i',str(source),
                '-map','0:v:0','-map','0:a:0?','-vf',"scale=720:720:force_original_aspect_ratio=decrease:force_divisible_by=2,fps=30",
                '-c:v','libx264','-preset','ultrafast','-crf','28','-threads','2','-c:a','aac','-b:a','96k','-movflags','+faststart',str(output)],timeout=600)
            info=probe_media(output);os.replace(output,target)
        return info
