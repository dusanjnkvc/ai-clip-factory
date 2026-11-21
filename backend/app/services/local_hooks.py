"""Small source-bound hook request, separate from final publication copy."""
import json,re
from pydantic import Field
from .local_analysis import Contract
from .media import PipelineError


class Hook(Contract):
    text: str=Field(min_length=1,max_length=80)
    editorial_score: float=Field(ge=0,le=100)
    support: str=Field(max_length=20)


class Hooks(Contract):
    hooks: list[Hook]=Field(min_length=3,max_length=3)


def generate_hooks(provider,plan,analysis):
    findings=[f for f in analysis['findings'] if any(s['start']<=f['timestamp']<s['end'] for s in plan['scenes'])]
    labels={f'S{i+1}':f['observation'] for i,f in enumerate(findings)}
    result=provider.structured(Hooks,
        'Write three brief truthful opening hooks for only this actual gaming edit. Cite one supplied support label per hook. '
        'Use at most nine words. Prefer a concrete observation or a simple curiosity question for gaming viewers. '
        'Avoid awkward analytical questions about tactical positioning, infrastructure, purpose or why a model sees something. '
        'Do not invent a kill, win, outcome, quote, measurement or reaction. '
        'Do not mention evidence, frames, analysis or implementation. Scores are editorial fit, not predicted views.',
        json.dumps({'visible_content':labels,'actual_speech':plan.get('transcript_excerpt','')[:400]}))
    support=' '.join(labels.values())+' '+plan.get('transcript_excerpt','')
    candidates=[]
    for hook in result.hooks:
        if hook.support not in labels:raise PipelineError('Opening hook cites unavailable source content.')
        numbers=set(re.findall(r'\d+(?:\.\d+)?',hook.text))-set(re.findall(r'\d+(?:\.\d+)?',support))
        claims=('victory','headshot','world record','guaranteed','you win','you won','multi-kill')
        if numbers or any(c in hook.text.lower() and c not in support.lower() for c in claims):
            continue
        candidates.append(hook.model_dump())
    if not candidates:
        return {'selected':plan['hook'],'candidates':[],'limitation':'Generated hooks failed source checks; retained the validated source opening.'}
    selected=max(candidates,key=lambda h:h['editorial_score'])
    return {'selected':selected['text'],'candidates':candidates,'limitation':'Source-supported editorial suggestions still require semantic review.'}
