"""Conservative experimental applicability, based on QA E1–E5 and E11."""
import pytest
from benchcheck.models import EvidenceContext, ExperimentMetadata
from benchcheck.evidence.sources import snippet_record, merge_sources
from benchcheck.evidence.conditions import find_materials, parse_electrolyte
from benchcheck.reasoning.hypotheses import evidence_plan


def context(**changes):
    return EvidenceContext(metadata=ExperimentMetadata(**{'electrode_material':'LiMn2O4','electrolyte':'1 M LiCl','solvent':'aqueous',**changes}))


def record(text,ctx=None,title='LiMn2O4 cyclic voltammetry'):
    return snippet_record({'title':title,'snippet':text,'link':'https://example.org/paper'},ctx or context(),'q')


def test_dissolved_analyte_is_not_electrode():
    r=record('Ferrocene cyclic voltammetry in 0.1 M TBAPF6 acetonitrile on glassy carbon.',context(process_type='dissolved_species',analyte='ferrocene',electrode_material='glassy carbon',electrolyte='0.1 M TBAPF6',solvent='non-aqueous'), 'Ferrocene on glassy carbon')
    rows={c['condition']:c for c in r['conditions']}
    assert rows['Analyte']['status']=='match'
    assert 'ferrocene' not in (rows['Electrode material']['paper'] or '')
    assert r['applicability']['level']=='condition-matched'


@pytest.mark.parametrize('text',[
 'LiMn2O4 was tested in 1 M LiNO3 aqueous electrolyte. LiCl was a precursor.',
 'LiMn2O4 was tested in 30 m ZnCl2 + 5 m LiCl aqueous electrolyte.',
 'LiMn2O4 was synthesized from aqueous LiCl precursor. Tests used LiTFSI in acetonitrile.',
 'LiMn2O4 in aqueous 1 M LiCl at 100 mV/s vs Li/Li+.'])
def test_differences_never_condition_matched(text):
    r=record(text,context(reference_electrode='sce',scan_rate={'value':1,'unit':'mV/s'}))
    assert r['applicability']['level']!='condition-matched'


def test_citation_does_not_establish_experimental_material():
    r=record('Prussian blue analogs [17, 18] have been studied. PTCDA was tested in aqueous KCl.',context(electrode_material='Prussian blue',electrolyte='0.1 M KCl'),title='Zinc PTCDA electrodes')
    assert next(x for x in r['conditions'] if x['condition']=='Electrode material')['status']!='match'


@pytest.mark.parametrize('name',['Prussian blue film','KFe[Fe(CN)6] film','Fe4[Fe(CN)6]3 film'])
def test_prussian_blue_canonicalization(name):
    keys={m.value for m in find_materials(name)}
    assert 'prussian_blue' in keys and not {'pba','ferricyanide'} & keys


def test_nonaqueous_and_molal():
    assert parse_electrolyte('non-aqueous electrolyte')['solvent']=='non-aqueous'
    assert parse_electrolyte('30 m ZnCl2')['concentrations'][0]['molar'] is None


def test_preserve_each_snippet():
    first=record('LiMn2O4 in aqueous 1 M LiCl cyclic voltammetry.')
    second=record('LiMn2O4 scan rate redox peaks in aqueous LiCl.')
    merged=merge_sources([first,second])[0]
    assert len(merged['snippets'])==2
    assert all(p['verification_label']=='matches search snippet' for p in merged['passages'])


def test_crossref_metadata_is_full_and_year_is_from_publication():
    import httpx
    from benchcheck.evidence.bibliography import lookup
    transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'message':{'container-title':['Advanced Energy Materials'],'published-online':{'date-parts':[[2026,7,28]]},'issued':{'date-parts':[[2027]]}}}))
    result=lookup('10.1234/test-qa',transport)
    assert result['venue']=='Advanced Energy Materials' and result['year']==2026


def test_domain_failure_memory_does_not_spend_another_call(tmp_path):
    import httpx
    from benchcheck.evidence.serpapi import SerpApiClient
    from benchcheck.settings import Settings
    calls=[]
    def respond(request):
        calls.append(request)
        return httpx.Response(200,json={'text_content':{'full':'Access denied robots.txt'}})
    client=SerpApiClient(Settings('test','live',tmp_path,3,5,5),httpx.MockTransport(respond))
    first=client.extract('https://example.org/a')
    second=client.extract('https://example.org/b')
    assert not first.ok and not second.ok and len(calls)==1
