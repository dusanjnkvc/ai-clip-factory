import math
import pytest
from pydantic import ValidationError
from test_pipeline import sample_plan,sample_transcript
from app.services.schemas import ClipPlan,Transcript,expanded_scenes,output_duration
from app.services.media import render_clip,run_media,ffmpeg_binary,timeline_words


def test_rate_ramp_caption_clock_and_real_render_with_accents(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCAL_AI_ENCODER','libx264')
    source=tmp_path/'original.mp4'
    run_media([ffmpeg_binary(),'-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=30','-f','lavfi','-i','sine=frequency=330',
        '-t','2.2','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(source)])
    plan=sample_plan();plan.update(show_hook=True,required_on_video_text=['#Required'],sound_cues=[{'kind':'click','start':.1,'volume':.1}],caption_color='#FFEA00')
    plan['scenes']=[{**plan['scenes'][0],'start':.2,'end':2,'speed':1,'speed_end':1.5,'freeze':.3,'zoom':1,'zoom_end':1.08,'effect':'flash','effect_intensity':.25,'shake':.003}]
    validated=ClipPlan.model_validate(plan);shots=expanded_scenes(validated.scenes)
    expected=sum(output_duration(s) for s in shots)
    mapped=timeline_words(validated,Transcript.model_validate(sample_transcript()))
    assert [w['word'] for w in mapped]==['See','the','change','now']
    assert all(0<=w['start']<w['end']<=expected for w in mapped)
    result=render_clip(source,plan,sample_transcript(),tmp_path/'edited.mp4')
    assert result['decode_verified'] and abs(result['duration']-expected)<.2
    assert source.is_file() and result['encoder']=='libx264'
    captions=(tmp_path/'edited.ass').read_text(encoding='utf-8')
    assert '#Required' in captions and '&H0000EAFF' in captions


def test_silent_aac_source_with_fit_and_manual_caption_is_playable(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCAL_AI_ENCODER','libx264')
    source=tmp_path/'silent.mp4'
    run_media([ffmpeg_binary(),'-v','error','-f','lavfi','-i','color=c=purple:size=320x180:rate=24','-f','lavfi','-i','anullsrc=r=48000:cl=stereo',
        '-t','2.2','-c:v','libx264','-c:a','aac','-shortest',str(source)])
    plan=sample_plan();plan.update(framing='fit',manual_captions=[{'start':.1,'end':1,'text':'User corrected caption'}])
    result=render_clip(source,plan,{},tmp_path/'result.mp4')
    assert result['decode_verified'] and result['subtitle_timing']=='cue'
    assert 'User corrected caption' in (tmp_path/'result.ass').read_text(encoding='utf-8')


def test_effect_limits_and_output_cues_reject_unsafe_settings():
    plan=sample_plan();plan['scenes'][0]['speed']=0
    with pytest.raises(ValidationError):ClipPlan.model_validate(plan)
    plan=sample_plan();plan['sound_cues']=[{'kind':'arbitrary_shell','start':0}]
    with pytest.raises(ValidationError):ClipPlan.model_validate(plan)
    plan=sample_plan();plan['manual_captions']=[{'start':0,'end':100,'text':'Too long'}]
    with pytest.raises(ValidationError):ClipPlan.model_validate(plan)


@pytest.mark.parametrize('preset,dimensions',[('portrait_720',(720,1280)),('square_1080',(1080,1080)),('landscape_1080',(1920,1080))])
def test_output_presets_render_actual_dimensions_and_keep_source(tmp_path,monkeypatch,preset,dimensions):
    monkeypatch.setenv('LOCAL_AI_ENCODER','libx264')
    source=tmp_path/'original.mp4'
    run_media([ffmpeg_binary(),'-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=24','-t','2.2','-c:v','libx264',str(source)])
    plan=sample_plan();plan.update(output_preset=preset,framing='fit',show_hook=True,hook='Known synthetic footage')
    rendered=render_clip(source,plan,{},tmp_path/'rendered.mp4')
    assert (rendered['width'],rendered['height'])==dimensions and rendered['decode_verified']
    assert source.exists()
