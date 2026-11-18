import zipfile
import pytest
from pypdf import PdfWriter
from app.services.campaign_documents import extract_document
from app.services.local import LocalPipelineService
from app.services.campaign_requirements import enforce_metadata
from app.services.compliance import check_compliance
from app.services.media import PipelineError
from test_pipeline import sample_plan, sample_metadata


def test_txt_docx_and_pdf_page_provenance(tmp_path):
    txt=tmp_path/'rules.txt'
    txt.write_text('Required hashtags:\n#Warzone #CallOfDuty #BrandCampaign\nRequired title: Exact wording\nRequired description: Paid partnership\nRequired on-screen text: #ad\nAllowed platforms: YouTube\nProhibited platforms: YouTube\nDuration: 8-12 seconds',encoding='utf-8')
    data=LocalPipelineService().analyze_campaign('',attachments=[{'filename':txt.name,'path':str(txt)}])
    assert data['rules']['required_hashtags']==['#Warzone','#CallOfDuty','#BrandCampaign']
    assert data['rules']['required_title']=='Exact wording'
    assert data['rules']['required_on_video_text']==['#ad']
    assert data['rules']['contradictions']
    assert all(item['source'].startswith('rules.txt:text') for item in data['evidence'])
    doc=tmp_path/'rules.docx'
    with zipfile.ZipFile(doc,'w') as archive:
        archive.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Brand: Exact Brand</w:t></w:r></w:p></w:body></w:document>')
    sections,_=extract_document(doc)
    assert sections[0]['text']=='Brand: Exact Brand'
    pdf=tmp_path/'scan.pdf';writer=PdfWriter();writer.add_blank_page(width=100,height=100)
    with pdf.open('wb') as stream: writer.write(stream)
    sections,warnings=extract_document(pdf)
    assert ':page 1:' in sections[0]['source']
    assert warnings or sections[0]['text']==''


def test_docx_entities_and_binary_text_rejected(tmp_path):
    doc=tmp_path/'bad.docx'
    with zipfile.ZipFile(doc,'w') as archive: archive.writestr('word/document.xml','<!DOCTYPE x><x/>')
    with pytest.raises(PipelineError): extract_document(doc)
    txt=tmp_path/'bad.txt';txt.write_bytes(b'abc\x00def')
    with pytest.raises(PipelineError): extract_document(txt)


def test_campaign_first_tags_exact_wording_and_noncompliance():
    rules={'required_hashtags':['#Warzone','#CallOfDuty','#BrandCampaign'],'required_title':'Exact Campaign',
           'required_description_phrases':['Paid partnership'],'allowed_platforms':['youtube']}
    variant=sample_metadata()['youtube']['variants'][0]
    variant.update(hashtags=['#Gaming','#warzone'],description='Actual event #FPS',caption='Actual event')
    enforced=enforce_metadata(variant,rules)
    assert enforced['hashtags']==['#Warzone','#CallOfDuty','#BrandCampaign','#Gaming','#FPS']
    assert enforced['title']=='Exact Campaign' and 'Paid partnership' in enforced['description']
    assert enforced['description'].index('#Warzone')<enforced['description'].index('#Gaming')
    metadata=sample_metadata();metadata['youtube']['variants'][0]=enforced
    render={'width':1080,'height':1920,'duration':2,'codec':'h264','has_audio':True,'decode_verified':True}
    result=check_compliance(sample_plan(),metadata,rules,True,render)
    assert next(c for c in result['checks'] if c['rule']=='hashtag_order_youtube')['status']=='PASS'
    metadata['youtube']['variants'][0]['hashtags'].reverse()
    result=check_compliance(sample_plan(),metadata,rules,True,render)
    assert result['status']=='FAIL'
