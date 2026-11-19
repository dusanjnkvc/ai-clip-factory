"""Local-only orchestration; existing native renderer and contracts are reused."""
import threading
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
        self.progress = progress or (lambda stage, percent: None)
        self.analysis = None
        self.bundle = {}

    def transcribe(self, source_path, cache_path=None):
        self._analyze(source_path)
        return self.analysis['transcript']

    def _analyze(self, path, transcript=None):
        self.analysis = LocalSourceAnalyzer(self.provider).analyze(path, transcript,
            game=self.options.get('game',''), context=self.options.get('context',''), cancel=self.cancel,
            progress=lambda stage,percent:self.progress(stage,5+int(percent*.45)))

    def plan_clips(self, transcript, rules, media_info, **kwargs):
        if self.analysis is None:
            supplied = transcript if transcript.get('words') or transcript.get('segments') else None
            self._analyze(media_info['path'], supplied)
        self.progress('Ranking source-grounded highlights',52)
        bounds=dict(rules)
        if self.options.get('studio'):
            bounds['min_duration']=max(rules.get('min_duration') or 1,self.options.get('minimum_duration',6))
            bounds['max_duration']=min(rules.get('max_duration') or 180,self.options.get('maximum_duration',20))
        ranked = rank_highlights(self.analysis,bounds,self.options.get('duration',20),platform=self.options.get('platform','youtube'))
        self.progress('Evaluating eligible edit plans locally',58)
        timelines = build_timelines(self.analysis,ranked,bounds,provider=self.provider,
                                    intensity=self.options.get('intensity','balanced'),cancel=self.cancel)
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
                plan['required_on_video_text']=rules.get('required_on_video_text',[])
                profile=self.options.get('editing_profile','automatic')
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
        self.progress('Writing and selecting source-grounded metadata locally',69)
        draft=self.bundle.get('drafts',{}).get(str(plan['start']),{})
        metadata_context={**self.analysis,'ending_checks':draft.get('ending_checks',self.bundle.get('ending_checks',[]))}
        if self.options.get('studio'):
            from .studio_metadata import generate_studio_package
            used=getattr(self,'used_titles',[])
            package=generate_studio_package(self.provider,plan,metadata_context,rules,research,used)
            self.used_titles=[*used,package['recommended']['title']]
            package['platform']='youtube'
            draft['hook_candidates']=package['hook_candidates']
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

    def render_clip(self,*args,**kwargs):
        if self.cancel.is_set(): raise InferenceCancelled('AUTO CREATE cancelled; original source preserved.')
        self.progress('Rendering the winning edit with native FFmpeg',76)
        result=super().render_clip(*args,**kwargs)
        if self.cancel.is_set(): raise InferenceCancelled('AUTO CREATE cancelled; original source preserved.')
        return result

    def evaluate_render(self,path,plan,metadata):
        from .viral_score import evaluate_render
        self.progress('Inspecting the actual rendered draft and calculating editorial scores',90)
        result=evaluate_render(path,plan,metadata,self.provider,self.bundle.get('research'))
        self.provider.unload()
        return result
