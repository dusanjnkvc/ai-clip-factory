"""Local-only orchestration; existing native renderer and contracts are reused."""
import threading
import os
from .pipeline import PipelineService
from .ollama_provider import OllamaProvider, InferenceCancelled
from .local_analysis import LocalSourceAnalyzer
from .local_highlights import rank_highlights
from .local_timeline import build_timelines
from .local_metadata import generate_package
from .trends import TrendResearch


class LocalAutoPipelineService(PipelineService):
    def __init__(self, options=None, progress=None):
        self.cancel = threading.Event()
        super().__init__(OllamaProvider(self.cancel))
        self.options = options or {}
        if self.options.get('studio'):
            # Keep one small model warm within a serial phase, then explicitly
            # unload it before rendering/transcription or leaving inference.
            self.provider.keep_alive_seconds=60
        self.progress = progress or (lambda stage, percent: None)
        self.analysis = None
        self.bundle = {}

    def transcribe(self, source_path, cache_path=None):
        self._analyze(source_path)
        return self.analysis['transcript']

    def _analyze(self, path, transcript=None):
        self.analysis = LocalSourceAnalyzer(self.provider).analyze(path, transcript,
            game=self.options.get('game',''), context=self.options.get('context',''), cancel=self.cancel,
            progress=lambda stage,percent:self.progress(stage,5+int(percent*.45)),
            max_frames={'fast':6,'balanced':12,'quality':24}.get(self.options.get('processing_mode','balanced')) if self.options.get('studio') and os.getenv('LOCAL_AI_FRAME_OVERRIDE','false').lower()!='true' else None)

    def plan_clips(self, transcript, rules, media_info, **kwargs):
        if self.analysis is None:
            supplied = transcript if transcript.get('words') or transcript.get('segments') else None
            if str(transcript.get('provider','')).startswith('faster_whisper'):
                supplied=None
            self._analyze(media_info['path'], supplied)
        self.progress('Ranking source-grounded highlights',52)
        bounds=dict(rules)
        if self.options.get('studio'):
            bounds['min_duration']=max(rules.get('min_duration') or 1,self.options.get('minimum_duration',6))
            bounds['max_duration']=min(rules.get('max_duration') or 180,self.options.get('maximum_duration',20))
        ranked = rank_highlights(self.analysis,bounds,self.options.get('duration',20),platform=self.options.get('platform','youtube'))
        self.progress('Evaluating eligible edit plans locally',58)
        timelines = build_timelines(self.analysis,ranked,bounds,provider=self.provider,
                                    intensity=self.options.get('intensity','balanced'),cancel=self.cancel,choose_styles=bool(self.options.get('studio')))
        self.bundle={'analysis_identity':self.analysis['cache_identity'],'ranking':ranked,'timelines':timelines}
        self.progress('Checking the proposed ending against actual source footage',61)
        from .local_tail import review_ending
        count=self.options.get('clip_count',1)
        candidates=sorted(timelines['candidates'],key=lambda c:c['id']!=timelines['winner_id'])[:count]
        self.bundle['drafts']={}
        plans=[]
        for candidate in candidates:
            plan,checks=review_ending(self.provider,media_info['path'],candidate['plan'],self.analysis,rules)
            if self.options.get('studio'):
                plan['content_type']='gaming'
                plan['framing']=self.options.get('framing','fit')
                plan['output_preset']=self.options.get('output_preset','portrait_1080')
                plan['required_on_video_text']=rules.get('required_on_video_text',[])
                profile=self.options.get('editing_profile','automatic')
                if profile=='automatic':
                    assessment=next(e for e in timelines['evaluations'] if e['candidate_id']==candidate['id'])
                    profile=assessment['recommended_style']
                    plan['semantic_notes'].append('AI Automatic selected '+profile+': '+assessment['rationale'])
                if profile=='clean':
                    for shot in plan['scenes']: shot.update(effect='none',transition='cut',zoom=1)
                    plan['subtitle_style']='clean'
                elif profile=='cinematic':
                    for shot in plan['scenes']: shot.update(effect='none',transition='fade',zoom=1)
                    plan['subtitle_style']='clean'
                elif profile=='gaming':
                    for shot in plan['scenes']: shot.update(effect='contrast',zoom=1.04)
                    plan['subtitle_style']='gaming'
                elif profile=='reference' and self.options.get('reference_profile'):
                    reference=self.options['reference_profile']
                    for shot in plan['scenes']: shot['transition']='fade' if reference.get('gentle_transitions') else 'cut'
                    observations=reference.get('visual_style_observations',[])
                    if any(o.get('caption_treatment')=='large_bold' for o in observations):plan['subtitle_style']='bold'
                    else:plan['subtitle_style']='clean'
                    if any(o.get('visual_treatment')=='high_contrast' for o in observations):
                        for shot in plan['scenes']:shot.update(effect='contrast',effect_intensity=.4)
                plan['edit_dna']['visual_effects']={'clean':'Clean Professional: restrained source cuts and readable captions','cinematic':'Cinematic: restrained fades and source-driven motion','gaming':'Gaming Viral: source-driven cuts and contrast'}.get(profile,'Measured reference pacing and supported transitions')
                plan['semantic_notes'].append('Automatic style follows source-bound pacing; reference features are measurements, not copied audiovisual content.')
            key=str(plan['start'])
            self.bundle['drafts'][key]={'ending_checks':checks,'style':candidate['style']}
            plans.append(plan)
        self.bundle['ending_checks']=self.bundle['drafts'][str(plans[0]['start'])]['ending_checks']
        if len(plans)<count:
            self.bundle['shortfall']='Source evidence supports fewer distinct moments than requested; no extra content was invented.'
        return plans

    def generate_metadata(self, plan, rules):
        if self.analysis is None: self._analyze(self.source_path)
        self.progress('Researching optional public sources',65)
        research=TrendResearch().research(self.options.get('game') or self.analysis['game_or_topic'],self.options.get('platform','youtube'))
        research['user_supplied_references']=self.options.get('research_examples',[])
        self.progress('Writing and selecting source-grounded metadata locally',69)
        draft=self.bundle.get('drafts',{}).get(str(plan['start']),{})
        metadata_context={**self.analysis,'ending_checks':draft.get('ending_checks',self.bundle.get('ending_checks',[]))}
        if self.options.get('studio'):
            from .local_hooks import generate_hooks
            from .local import LocalPipelineService
            hooks=generate_hooks(self.provider,plan,metadata_context)
            plan['hook']=hooks['selected'];plan['show_hook']=True
            draft['hook_candidates']=hooks['candidates']
            self.bundle.update(research=research,platform='youtube')
            self.provider.unload()
            # This temporary source package is replaced after actual-render
            # observations exist. It is never presented as final AI copy.
            return LocalPipelineService().generate_metadata(plan,rules)
        else:
            package=generate_package(self.provider,plan,metadata_context,rules,research,self.options.get('platform','youtube'))
        plan['hook']=package['recommended']['opening_hook']
        plan['title']=package['recommended']['title']
        plan['show_hook']=True
        self.bundle.update(research=research,recommended=package['recommended'],platform=package['platform'])
        draft.update(recommended=package['recommended'],research=research)
        self.last_metadata=package['metadata']
        self.provider.unload()
        return package['metadata']

    def finalize_metadata(self,plan,metadata,evaluation,rules):
        reviews=evaluation.get('visual',{}).get('individual_sample_reviews',[]) if evaluation else []
        frames=evaluation.get('visual',{}).get('sampled_frames',[]) if evaluation else []
        if not reviews or not all(r.get('visible_content') for r in reviews):
            for block in metadata.values():
                block['generation_status']='unavailable'
                for variant in block['variants']:variant['reasoning']='Actual-render content review is unavailable. Enter and review publication text manually.'
            return metadata
        from .schemas import ClipPlan,expanded_scenes,output_duration
        from .studio_metadata import generate_studio_package
        findings=[];shots=expanded_scenes(ClipPlan.model_validate(plan).scenes)
        for frame,review in zip(frames,reviews):
            offset=0;source_time=shots[-1].end-.001
            for shot in shots:
                duration=output_duration(shot)
                if frame['timestamp']<offset+duration:
                    source_time=min(shot.end-.001,shot.start+max(0,frame['timestamp']-offset)*shot.speed);break
                offset+=duration
            findings.append({'timestamp':source_time,'evidence_id':'rendered:'+frame['evidence_id'],
                'observation':review['visible_content']})
        context={**self.analysis,'findings':findings,'ending_checks':[],
            'game_or_topic':self.options.get('game') or rules.get('game_name') or 'Exact game title not established',
            'topic_uncertainty':'Use only the actual rendered observations below, not overall-source scene guesses.'}
        self.progress('Writing platform text from actual rendered content',94)
        try:
            package=generate_studio_package(self.provider,plan,context,rules,self.bundle.get('research',{}),getattr(self,'used_titles',[]),self.options.get('history'))
            result=package['metadata']
            for block in result.values():
                block['generation_status']='generated'
                for variant in block['variants']:variant['opening_hook']=plan['hook']
            plan['title']=package['recommended']['title']
            self.used_titles=[*getattr(self,'used_titles',[]),plan['title']]
            return result
        except Exception as exc:
            if self.cancel.is_set():raise
            for block in metadata.values():
                block['generation_status']='unavailable'
                for variant in block['variants']:variant['reasoning']='Final metadata generation failed; manual correction required: '+str(exc)[:200]
            return metadata
        finally:
            try:self.provider.unload()
            except Exception:pass

    def render_clip(self,*args,**kwargs):
        if self.cancel.is_set(): raise InferenceCancelled('AUTO CREATE cancelled; original source preserved.')
        self.progress('Rendering the edited draft with native FFmpeg',76)
        result=super().render_clip(*args,**kwargs)
        self.last_render_info=result
        if self.cancel.is_set(): raise InferenceCancelled('AUTO CREATE cancelled; original source preserved.')
        return result

    def evaluate_render(self,path,plan,metadata):
        from .viral_score import evaluate_render
        self.progress('Inspecting the actual rendered draft and calculating editorial scores',90)
        try:
            return evaluate_render(path,plan,metadata,self.provider,self.bundle.get('research'),getattr(self,'last_render_info',None))
        except Exception as exc:
            if self.cancel.is_set():raise
            return {'status':'unavailable','reason':'Actual-render evaluation failed: '+str(exc)[:400],
                'platforms':{},'suggestions':[],'publish_ready':False}
        finally:
            try:self.provider.unload()
            except Exception:pass
