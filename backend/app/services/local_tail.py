"""Bounded local visual check of a proposed ending, before metadata/rendering."""
import base64
import tempfile
from pathlib import Path
from typing import Literal
from pydantic import Field
from .local_analysis import Contract
from .schemas import ClipPlan, CampaignRules
from . import media


class Ending(Contract):
    state: Literal['content','loading','blank','uncertain']
    confidence: Literal['low','medium','high']
    reason: str = Field(max_length=160)


def review_ending(provider, source, raw_plan, analysis, rules):
    plan=ClipPlan.model_validate(raw_plan).model_dump()
    minimum=max(1,CampaignRules.model_validate(rules).min_duration or 1)
    checks=[]
    with tempfile.TemporaryDirectory(prefix='acf-ending-') as directory:
        image=Path(directory)/'ending.jpg'
        for attempt in range(2):
            timestamp=max(plan['scenes'][-1]['start'],plan['scenes'][-1]['end']-.3)
            media.run_media([media.ffmpeg_binary(),'-v','error','-y','-ss',str(timestamp),
                *media.safe_input_options(source),'-i',str(source),'-frames:v','1','-vf','scale=384:-2',str(image)],timeout=90)
            verdict=provider.structured(Ending,
                'Classify only this actual final source frame. A real card reveal/game animation is content. '
                'Use loading only for a generic application/network loading spinner that interrupts the content. '
                'Use blank for an empty screen. Do not infer outcomes or whether a story is true. Be uncertain when ambiguous.',
                'Check whether this proposed final frame is meaningful content or an obvious loading interruption.',
                [{'timestamp':timestamp,'data_url':'data:image/jpeg;base64,'+base64.b64encode(image.read_bytes()).decode()}])
            checks.append({'source_timestamp':timestamp,**verdict.model_dump(),'origin':'local_model_unverified'})
            if verdict.state not in {'loading','blank'} or verdict.confidence!='high' or attempt==1:
                break
            # Only shorten; never add material or move source events out of order.
            total=sum(s['end']-s['start'] for s in plan['scenes'])
            new_duration=max(minimum,total*.5)
            if new_duration>=total-.3: break
            remaining=new_duration;scenes=[]
            for scene in plan['scenes']:
                if remaining<=.05: break
                shot={**scene,'end':min(scene['end'],scene['start']+remaining)}
                scenes.append(shot);remaining-=shot['end']-shot['start']
            if not any(any(s['start']<=f['timestamp']<s['end'] for s in scenes) for f in analysis['findings']): break
            plan['scenes']=scenes;plan['end']=scenes[-1]['end']
            plan['transcript_excerpt']=' '.join(s['text'] for s in analysis['transcript'].get('segments',[])
                if any(shot['start']<=s['start'] and s['end']<=shot['end'] for shot in scenes))
            plan['semantic_notes'].append('Ending shortened after an uncertain local-model loading/blank-screen check; review actual result.')
    return ClipPlan.model_validate(plan).model_dump(),checks
