import pytest
from test_pipeline import sample_plan,sample_metadata
from app.services.viral_score import evaluate_render,score_metadata,weights
from app.services.media import run_media,ffmpeg_binary,PipelineError


def test_actual_render_samples_score_components_and_metadata_changes(tmp_path):
    path=tmp_path/'render.mp4'
    run_media([ffmpeg_binary(),'-v','error','-f','lavfi','-i','testsrc2=size=180x320:rate=12','-t','2','-c:v','libx264',str(path)])
    class Observer:
        calls=0
        def structured(self,schema,system,prompt,images):
            self.calls+=1
            assert len(images)==1 and all(i['data_url'].startswith('data:image/jpeg;base64,') for i in images)
            return schema.model_validate({'clarity':70,'visual_interest':60,'readability':40,'framing':40,'observed_issue':'Controlled classifier of actual JPEGs.','uncertainty':'Not a semantic acceptance test.'})
    result=evaluate_render(path,sample_plan(),sample_metadata(),Observer())
    assert len(result['visual']['sampled_frames'])==3 and result['visual']['artifact_sha256']
    assert result['visual']['decode_verified'] and result['platforms']['youtube']['confidence']=='low'
    assert {x['action'] for x in result['suggestions']}=={'fit_gameplay','clean_captions'}
    score=result['platforms']['youtube']
    assert score['score']==pytest.approx(sum(score['components'][k]*score['weights'][k] for k in score['weights']),abs=.02)
    metadata=sample_metadata();metadata['youtube']['variants'][0]['title']=' '.join(['Repeated']*70)
    changed=score_metadata(result['visual'],metadata)
    assert changed['youtube']['components']['title']<score['components']['title']
    assert changed['youtube']['components']['entertainment']==score['components']['entertainment']
    assert changed['youtube']['components']['research']==0


def test_score_weights_reject_invalid_and_normalize(monkeypatch):
    monkeypatch.setenv('VIRAL_SCORE_WEIGHTS','{"hook": 1}')
    with pytest.raises(PipelineError): weights()
