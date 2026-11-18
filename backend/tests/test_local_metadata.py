import pytest
from test_pipeline import sample_plan
from app.services.local_metadata import generate_package
from app.services.media import PipelineError


class Provider:
    evidence='frame-1'
    def structured(self,schema,*args):
        return schema.model_validate({'variants':[{'title':'Actual source '+str(i),'description':'Source description','caption':'Source description','hashtags':['#source'],'score':i*20,'evidence_ids':[self.evidence]} for i in range(3)]})


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
        generate_package(provider,sample_plan(),{'findings':[{'timestamp':.5,'evidence_id':'frame-1'}]}, {}, {})
