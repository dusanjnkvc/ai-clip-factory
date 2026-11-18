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
        ranked = rank_highlights(self.analysis,rules,self.options.get('duration',20),platform=self.options.get('platform','youtube'))
        self.progress('Evaluating eligible edit plans locally',58)
        timelines = build_timelines(self.analysis,ranked,rules,provider=self.provider,
                                    intensity=self.options.get('intensity','balanced'),cancel=self.cancel)
        self.bundle={'analysis_identity':self.analysis['cache_identity'],'ranking':ranked,'timelines':timelines}
        self.progress('Checking the proposed ending against actual source footage',61)
        from .local_tail import review_ending
        plan,checks=review_ending(self.provider,media_info['path'],timelines['winner_plan'],self.analysis,rules)
        self.bundle['ending_checks']=checks
        self.bundle['timelines']['winner_plan']=plan
        return [plan]

    def generate_metadata(self, plan, rules):
        if self.analysis is None: self._analyze(self.source_path)
        self.progress('Researching optional public sources',65)
        research=TrendResearch().research(self.options.get('game') or self.analysis['game_or_topic'],self.options.get('platform','youtube'))
        self.progress('Writing and selecting source-grounded metadata locally',69)
        metadata_context={**self.analysis,'ending_checks':self.bundle.get('ending_checks',[])}
        package=generate_package(self.provider,plan,metadata_context,rules,research,self.options.get('platform','youtube'))
        plan['hook']=package['recommended']['opening_hook']
        plan['title']=package['recommended']['title']
        plan['show_hook']=True
        self.bundle.update(research=research,recommended=package['recommended'],platform=package['platform'])
        self.provider.unload()
        return package['metadata']

    def render_clip(self,*args,**kwargs):
        if self.cancel.is_set(): raise InferenceCancelled('AUTO CREATE cancelled; original source preserved.')
        self.progress('Rendering the winning edit with native FFmpeg',76)
        result=super().render_clip(*args,**kwargs)
        if self.cancel.is_set(): raise InferenceCancelled('AUTO CREATE cancelled; original source preserved.')
        return result
