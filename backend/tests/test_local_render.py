from test_pipeline import sample_plan, sample_transcript
from app.services.media import render_clip,run_media,ffmpeg_binary

def test_native_real_animated_edit_and_mute(tmp_path):
    source=tmp_path/'source.mp4'
    run_media([ffmpeg_binary(),'-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=30','-f','lavfi','-i','sine=frequency=440','-t','2.2','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(source)])
    plan=sample_plan();plan.update(show_hook=True,hook='Actual source test',audio_treatment='mute')
    for shot in plan['scenes']: shot.update(crop_x_end=.8,crop_y_end=.6,transition='fade',effect='contrast')
    result=render_clip(source,plan,sample_transcript(),tmp_path/'edited.mp4')
    assert result['decode_verified'] and result['width']==1080 and result['height']==1920
    assert 'Actual source test' in (tmp_path/'edited.ass').read_text(encoding='utf-8')
    audio=run_media([ffmpeg_binary(),'-v','info','-i',str(tmp_path/'edited.mp4'),'-vn','-af','volumedetect','-f','null','-'])
    assert 'max_volume: -91' in audio.stderr or 'max_volume: -inf' in audio.stderr
