from app.services.studio_metadata import generate_studio_package,Titles
from app.services.local_metadata import Packages
from app.services.media import PipelineError
from test_pipeline import sample_plan
import pytest


class Provider:
    def structured(self,schema,system,prompt,*args):
        if schema is Titles:
            return schema.model_validate({'titles':[{'title':f'Actual card detail {i}','editorial_score':70+i,'reason':'Controlled title contract.'} for i in range(3)]})
        platform='tiktok' if '"platform": "tiktok"' in prompt else 'youtube'
        return schema.model_validate({'variants':[{'title':platform+f' source {i}','description':platform+' actual source description',
            'opening_hook':'A card appears','hashtags':['#Optional'],'score':60+i,'evidence_ids':['S1']} for i in range(3)]})


def test_three_youtube_titles_and_platform_specific_text_preserve_campaign_order():
    package=generate_studio_package(Provider(),sample_plan(),{'findings':[{'timestamp':.5,'evidence_id':'actual-1','observation':'A visible card appears.'}]},
        {'required_hashtags':['#Mandatory']},{'status':'unavailable'})
    metadata=package['metadata']
    assert len(metadata['youtube']['title_candidates'])==3
    assert package['recommended']['title']=='Actual card detail 2'
    assert metadata['tiktok']['variants'][0]['description'].startswith('tiktok')
    assert all(v['hashtags'][0]=='#Mandatory' for p in metadata.values() for v in p['variants'])
    assert len(package['hook_candidates'])==3


def test_exact_campaign_title_overrides_alternative_titles():
    package=generate_studio_package(Provider(),sample_plan(),{'findings':[{'timestamp':.5,'evidence_id':'actual-1','observation':'A visible card appears.'}]},
        {'required_title':'Exact mandatory title'},{'status':'unavailable'})
    assert package['recommended']['title']=='Exact mandatory title'
    assert len(package['metadata']['youtube']['title_candidates'])==1


def test_final_text_deduplicates_embedded_tags_and_checks_combined_limits():
    from app.services.publication_text import publication_text
    from app.services.compliance import check_compliance
    from test_pipeline import sample_metadata
    meta=sample_metadata()
    value=meta['tiktok']['variants'][0]
    value.update(caption='Review #Mandatory',hashtags=['#Mandatory','#Other'])
    assert publication_text(value,'tiktok')=='Review #Mandatory\n\n#Other'
    value.update(caption='x'*2199,hashtags=['#Mandatory'])
    meta['tiktok']['recommended_index']=0
    checks=check_compliance(sample_plan(),meta,{},True,{'width':1080,'height':1920,'duration':2,'has_audio':True,'decode_verified':True,'codec':'h264'})['checks']
    assert next(c for c in checks if c['rule']=='publication_length_tiktok')['status']=='FAIL'


def test_automatic_copy_recovery_uses_actual_render_observations_and_mandatory_tags():
    from app.services.studio_metadata import observation_package
    result=observation_package(sample_plan(),{'findings':[{'observation':'A purple snake curves around an orange snake.'}]},{'required_hashtags':['#Bandit','#Roblox']})
    assert len(result['youtube']['title_candidates'])==3
    assert len({v['title'] for v in result['youtube']['variants']})==3
    for platform in result.values():
        assert platform['generation_status']=='generated'
        for v in platform['variants']:
            assert 'purple snake' in v['description']
            assert v['hashtags'][:2]==['#Bandit','#Roblox']
    with pytest.raises(PipelineError):observation_package(sample_plan(),{'findings':[]},{})


def test_overlay_only_render_findings_cannot_become_publication_copy():
    from app.services.studio_metadata import observation_package,rendered_context
    text='Black background with yellow text reading ALL NEW.'
    with pytest.raises(PipelineError):observation_package(sample_plan(),{'findings':[{'observation':text}]},{})
    context=rendered_context(sample_plan(),{'visual':{'observation_contract':'original_scene_only_v3','sampled_frames':[{'timestamp':0,'evidence_id':'frame-1'},{'timestamp':.8,'evidence_id':'frame-2'}],
        'individual_sample_reviews':[{'visible_content':text},{'visible_content':'Two gloved hands above a cityscape.'}]}})
    assert len(context['findings'])==1 and context['findings'][0]['evidence_id']=='rendered:frame-2'
