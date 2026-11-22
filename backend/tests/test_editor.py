import io,copy,wave
import pytest
from PIL import Image
from test_backend import environment,register,seed_clip
from test_pipeline import sample_plan,sample_metadata
from test_studio import enable
from app.models import RenderedClip,EditingPlan
from app.services.schemas import ClipPlan

def editor():
    return {'schema_version':1,'layers':[],'source_volume':1,'background':'#000000','caption':{'preset':'Gaming','size':68,'color':'#FFFFFF','highlight':'#FFE600','outline':'#111111','outline_width':2,'background':'#000000B0','y':.82,'opacity':1,'rotation':0,'letter_spacing':0,'line_height':1.2,'weight':700,'uppercase':False,'animation':'none'}}

def layer(asset_id=None):
    return {'id':'test-layer','kind':'image' if asset_id else 'text','name':'Owned logo' if asset_id else 'User text','start':0,'end':1.8,'x':.1,'y':.2,'width':.4,'height':.2,'rotation':15,'opacity':.7,'visible':True,'locked':False,'text':'Literal <text>','asset_id':asset_id,'font_size':64,'font_family':'Noto Sans','font_weight':700,'color':'#FFFFFF','background':'#00000000','outline_color':'#111111','outline_width':2,'shadow':True,'align':'center','animation':'fade','volume':1,'fade_in':0,'fade_out':0,'trim_start':0,'duck':False}

def prepare(environment,monkeypatch):
    client,factory,config=environment;user=register(client);clip,campaign=seed_clip(factory,user['id'],config);enable(monkeypatch)
    return client,factory,config,clip,campaign

def test_editor_schema_rejects_bad_time_and_asset_injection():
    plan=sample_plan();plan['editor']=editor();plan['editor']['layers']=[layer()]
    parsed=ClipPlan.model_validate(plan);assert parsed.editor.layers[0].text=='Literal <text>'
    for field,value in [('end',99),('opacity',float('nan')),('asset_id','https://untrusted.test/file')]:
        bad=copy.deepcopy(plan);bad['editor']['layers'][0][field]=value
        with pytest.raises(ValueError):ClipPlan.model_validate(bad)

def test_render_defaults_preserve_existing_preferences_and_review_version(environment,monkeypatch):
    client,_,_,clip,_=prepare(environment,monkeypatch)
    assert client.get('/api/studio/preferences').json()['output_fps']==30
    value={'processing_mode':'fast','output_preset':'portrait_720','output_fps':60}
    assert client.put('/api/studio/preferences',json=value).json()==value
    assert client.get('/api/studio/preferences').json()==value
    assert client.put('/api/studio/preferences',json={**value,'output_fps':999}).status_code==422
    assert client.post(f'/api/clips/{clip}/review',json={'version':999,'note':'Wrong version must not receive review evidence.'}).status_code==409

def test_draft_autosave_is_version_checked_without_job_or_video_mutation(environment,monkeypatch):
    client,factory,config,clip,_=prepare(environment,monkeypatch)
    plan=sample_plan();plan['editor']=editor();plan['editor']['layers']=[layer()]
    response=client.put(f'/api/editor/drafts/{clip}',json={'revision':0,'plan':plan,'metadata':sample_metadata()})
    assert response.status_code==200,response.text
    assert response.json()['revision']==1
    assert client.get(f'/api/editor/drafts/{clip}').json()['plan']['editor']['layers'][0]['rotation']==15
    assert client.put(f'/api/editor/drafts/{clip}',json={'revision':0,'plan':plan,'metadata':sample_metadata()}).status_code==409
    with factory() as db:
        row=db.get(RenderedClip,clip);assert row.current_version==1 and row.storage_key=='not-rendered'
        assert db.get(EditingPlan,row.editing_plan_id).plan=={}

def test_owned_images_reencode_and_references_prevent_archiving(environment,monkeypatch):
    client,_,_,clip,_=prepare(environment,monkeypatch)
    file=io.BytesIO();Image.new('RGBA',(40,30),(180,50,240,100)).save(file,'PNG')
    response=client.post('/api/editor/assets',files={'file':('transparent.png',file.getvalue(),'image/png')});assert response.status_code==200,response.text
    a=response.json();assert 'storage_key' not in a and a['width']==40
    assert client.get(a['url']).headers['content-type']=='image/png'
    plan=sample_plan();plan['editor']=editor();plan['editor']['layers']=[layer(a['id'])]
    assert client.put(f'/api/editor/drafts/{clip}',json={'revision':0,'plan':plan,'metadata':sample_metadata()}).status_code==200
    assert client.delete('/api/editor/assets/'+a['id']).status_code==409
    assert client.post('/api/editor/assets',files={'file':('attack.svg',b'<svg><script>alert(1)</script></svg>','image/svg+xml')}).status_code==422
    assert client.post('/api/editor/assets',files={'file':('fake.png',b'not an image','image/png')}).status_code==422
    assert client.get('/api/editor/assets/not-owned/content').status_code==404

def test_audio_assets_above_json_limit_are_canonicalized(environment,monkeypatch):
    client,_,_,_,_=prepare(environment,monkeypatch)
    content=io.BytesIO()
    with wave.open(content,'wb') as wav:
        wav.setparams((1,2,48000,0,'NONE','not compressed'));wav.writeframes(b'\0\0'*48000*12)
    response=client.post('/api/editor/assets',files={'file':('owned.wav',content.getvalue(),'audio/wav')})
    assert response.status_code==200,response.text
    asset=response.json();assert asset['kind']=='audio' and asset['duration']==12
    downloaded=client.get(asset['url'])
    with wave.open(io.BytesIO(downloaded.content),'rb') as wav:assert wav.getnchannels()==2 and wav.getframerate()==48000

def test_duplicate_project_has_independent_plan_media_and_review(environment,monkeypatch):
    client,factory,_,clip,_=prepare(environment,monkeypatch)
    from app.models import SourceVideo
    from app.storage import materialize,put_file
    with factory() as db:
        original=db.get(RenderedClip,clip);source=db.get(SourceVideo,original.source_id);db.get(EditingPlan,original.editing_plan_id).plan=sample_plan();original.metadata_json=sample_metadata()
        with materialize(source.storage_key) as path:put_file(path,original.storage_key)
        db.commit()
    response=client.post(f'/api/editor/drafts/{clip}/duplicate');assert response.status_code==200,response.text
    copy_id=response.json()['id'];assert copy_id!=clip
    with factory() as db:
        original=db.get(RenderedClip,clip);duplicate=db.get(RenderedClip,copy_id)
        assert duplicate.editing_plan_id!=original.editing_plan_id and duplicate.storage_key!=original.storage_key
        assert duplicate.current_version==1 and not duplicate.draft_approved
    assert client.get(f'/api/clips/{copy_id}/video').content==client.get(f'/api/clips/{clip}/video').content

def test_template_and_proxy_reuse_existing_source_without_inference(environment,monkeypatch):
    client,factory,_,clip,campaign=prepare(environment,monkeypatch)
    state=editor();state['layers']=[layer()]
    template=client.post('/api/editor/templates',json={'name':'Saved design','editor':state,'duration':2,'campaign_id':campaign})
    assert template.status_code==200,template.text
    assert client.get('/api/editor/templates').json()[0]['editor']['layers']==state['layers']
    plan=sample_plan();plan['editor']=state
    from app.services.ollama_provider import OllamaProvider
    monkeypatch.setattr(OllamaProvider,'structured',lambda *a,**k:pytest.fail('Editor preview must not perform AI inference'))
    preview=client.post(f'/api/editor/drafts/{clip}/preview',json={'plan':plan});assert preview.status_code==200,preview.text
    assert client.get(preview.json()['videoUrl']).status_code==200
    assert preview.json()['editor']['layers'][0]['text']=='Literal <text>'
