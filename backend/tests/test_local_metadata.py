import pytest
from test_pipeline import sample_plan
from app.services.local_metadata import generate_package
from app.services.media import PipelineError


class Provider:
    evidence='S1'
    def structured(self,schema,*args):
        return schema.model_validate({'variants':[{'title':'Actual source '+str(i),'description':'Source description','opening_hook':'Watch the source change','hashtags':['#source'],'score':i*20,'evidence_ids':[self.evidence]} for i in range(3)]})


def test_one_selected_package_retains_required_text_and_internal_alternatives():
    result=generate_package(Provider(),sample_plan(),{'findings':[{'timestamp':.5,'evidence_id':'frame-1','observation':'Actual source'}]},
                            {'required_links':['https://example.com/required'],'required_hashtags':['#ad']},{'status':'unavailable'})
    assert result['recommended']['title']=='Actual source 2'
    assert '#ad' in result['recommended']['hashtags']
    assert 'https://example.com/required' in result['recommended']['description']
    assert len(result['metadata']['youtube']['variants'])==3
    assert result['research_classification']=='general_relevant_suggestion'


def test_unknown_metadata_evidence_cannot_be_selected():
    provider=Provider();provider.evidence='invented'
    with pytest.raises(PipelineError,match='outside'):
        generate_package(provider,sample_plan(),{'findings':[{'timestamp':.5,'evidence_id':'frame-1','observation':'Actual source'}]}, {}, {})


def test_unsupported_hype_uses_actual_visible_text_and_filters_production_tags():
    class Hype(Provider):
        def structured(self,schema,*args):
            result=super().structured(schema,*args)
            for variant in result.variants:
                variant.opening_hook='This card will change everything'
                variant.hashtags=['#CardReveal','#VisualAnchor']
            return result
    result=generate_package(Hype(),sample_plan(),{'findings':[{'timestamp':.5,'evidence_id':'frame-1','observation':"A card with 'REVEALING...' text."}]},{},{})
    assert result['recommended']['opening_hook']=='REVEALING...'
    assert result['recommended']['hashtags']==['#CardReveal']


def test_invented_numeric_hook_does_not_reach_rendering():
    class Numeric(Provider):
        def structured(self,schema,*args):
            result=super().structured(schema,*args)
            for variant in result.variants:
                variant.opening_hook='From 300 feet up'
            return result
    plan=sample_plan()
    result=generate_package(Numeric(),plan,{'findings':[{'timestamp':.5,'evidence_id':'frame-1','observation':'Aerial view of a city'}]},{},{})
    assert result['recommended']['opening_hook']==plan['hook']
