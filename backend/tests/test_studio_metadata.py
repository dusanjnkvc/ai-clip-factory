from app.services.studio_metadata import generate_studio_package,Titles
from app.services.local_metadata import Packages
from app.services.media import PipelineError
from test_pipeline import sample_plan
import pytest


class Provider:
    def structured(self,schema,system,prompt,*args):
        if schema is Titles:
            return schema.model_validate({'titles':[{'title':f'Actual card detail {i}','editorial_score':70+i,'reason':'Controlled title contract.'} for i in range(5)]})
        platform='tiktok' if '"platform": "tiktok"' in prompt else 'youtube'
        return schema.model_validate({'variants':[{'title':platform+f' source {i}','description':platform+' actual source description',
            'opening_hook':'A card appears','hashtags':['#Optional'],'score':60+i,'evidence_ids':['S1']} for i in range(3)]})


def test_five_youtube_titles_and_platform_specific_text_preserve_campaign_order():
    package=generate_studio_package(Provider(),sample_plan(),{'findings':[{'timestamp':.5,'evidence_id':'actual-1','observation':'A visible card appears.'}]},
        {'required_hashtags':['#Mandatory']},{'status':'unavailable'})
    metadata=package['metadata']
    assert len(metadata['youtube']['title_candidates'])==5
    assert package['recommended']['title']=='Actual card detail 4'
    assert metadata['tiktok']['variants'][0]['description'].startswith('tiktok')
    assert all(v['hashtags'][0]=='#Mandatory' for p in metadata.values() for v in p['variants'])
    assert len(package['hook_candidates'])==3


def test_exact_campaign_title_overrides_five_alternative_titles():
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
