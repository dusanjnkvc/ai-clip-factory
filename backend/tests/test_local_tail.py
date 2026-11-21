from test_pipeline import sample_plan
from app.services.local_tail import review_ending
from app.services.media import ffmpeg_binary,run_media


def test_loading_tail_trim_is_source_bounded_and_keeps_evidence(tmp_path):
    source=tmp_path/'actual.mp4'
    run_media([ffmpeg_binary(),'-v','error','-f','lavfi','-i','color=c=purple:size=160x90:rate=12','-t','2.2','-c:v','libx264',str(source)])
    class Observer:
        calls=0
        def structured(self,schema,*args):
            self.calls+=1
            return schema.model_validate({'state':'loading' if self.calls==1 else 'content','confidence':'high','reason':'Controlled classifier, actual JPEG supplied.'})
    plan,checks=review_ending(Observer(),source,sample_plan(),{'findings':[{'timestamp':.5}],'transcript':{'segments':[]}}, {})
    assert len(checks)==2 and checks[0]['state']=='loading'
    assert sum(s['end']-s['start'] for s in plan['scenes'])==1
    assert plan['start']==.2 and plan['end']==1.2
