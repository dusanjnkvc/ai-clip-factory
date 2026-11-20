import pytest
from app.services.campaign_ai import analyze_campaign
from app.services.media import PipelineError


class Provider:
    quote='You must include #Warzone before #Partner.'
    def structured(self,schema,*args):
        return schema.model_validate({'rules':[{'field':'required_hashtags','value_json':'["#Warzone", "#Partner"]','quote':self.quote}],
            'uncertainty':'Other wording requires human review.'})
    def unload(self):pass


def test_natural_language_rule_extraction_requires_actual_exact_quotes():
    result=analyze_campaign(Provider(),'You must include #Warzone before #Partner.',[])
    assert result['rules']['required_hashtags']==['#Warzone','#Partner']
    assert result['evidence'][0]['source']=='brief' and result['review_required']
    provider=Provider();provider.quote='Fabricated rule from another source.'
    with pytest.raises(PipelineError,match='absent'):
        analyze_campaign(provider,'You must include #Warzone before #Partner.',[])


def test_invalid_model_value_preserves_independent_rules_and_requires_review():
    class Invalid(Provider):
        def structured(self,schema,*args):
            return schema.model_validate({'rules':[{'field':'allowed_platforms','value_json':'["YouTube"]','quote':'Allowed platforms: YouTube.'}],'uncertainty':''})
    result=analyze_campaign(Invalid(),'Allowed platforms: YouTube.\nRequired hashtags: #Required',[])
    assert result['rules']['required_hashtags']==['#Required']
    assert any('failed validation' in note for note in result['rules']['uncertainties'])
    assert result['review_required']
