"""Execute the notebook's self-contained numerical reproductions against TestClient."""
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from benchcheck.app import app


@pytest.mark.parametrize('case', range(64,84,2))
def test_notebook_analysis(case):
    results=[]
    def post(url,**kwargs):
        response=TestClient(app).post(url.removeprefix('http://127.0.0.1:8000'),**kwargs)
        assert response.status_code == 200, response.text
        if url.endswith('/analyze'):
            results.append(response.json())
        return response
    exec((Path(__file__).parent/'qa_cases'/f'analysis_{case}.py').read_text(),{'requests':SimpleNamespace(post=post)})
    assert results
    for r in results:
        triggered={h['id'] for h in r['hypotheses'] if h['triggered']}
        if case in (64,76):
            assert 'ec_chemical_step' in triggered
            assert not {'truncated_return','side_reaction_vertex'} & triggered
        elif case == 66:
            assert not r['selected']['forward']['peaks']
            assert not {'irreversible_loss','ec_chemical_step'} & triggered
        elif case == 68:
            assert r['selected']['pairs'][0]['height_ratio'] == pytest.approx(1,abs=.05)
            assert 'asymmetric_return' not in triggered
        elif case == 70:
            assert 'truncated_return' not in triggered
        elif case == 72 and r['metadata']['process_type']=='unknown':
            assert 'irreversible_loss' not in triggered
            assert any('Process type not set' in n for n in r['notices'])
        elif case == 74:
            assert r['noise_sigma'] == pytest.approx(1e-6,rel=.15)
            assert len(r['selected']['forward']['peaks'])==1
        elif case == 78:
            assert 'kinetic_limitation' in triggered
        elif case == 82:
            assert 'side_reaction_vertex' not in triggered
            assert not any('largest forward peak' in t for h in r['hypotheses'] for t in h['observations'])


def test_plot_decimation_preserves_extrema_and_peak_indices():
    import numpy as np
    from benchcheck.cv.analysis import analyze
    from benchcheck.cv.parsing import parse_table
    from benchcheck.cv.plot_data import decimate
    from tests.test_analysis import csv_bytes,base_config
    e=np.r_[np.linspace(0,1,15000),np.linspace(1,0,15000)]
    t=np.arange(len(e))*.01
    i=np.where(np.arange(len(e))<15000,1.,-1.)*np.exp(-((e-.5)/.05)**2)*1e-3
    result=analyze(parse_table(csv_bytes(t,e,i)),base_config())
    maximum=max(result['data']['i']); minimum=min(result['data']['i'])
    reduced=decimate(result,2000)
    assert len(reduced['data']['E'])<=2000
    assert max(reduced['data']['i'])==maximum and min(reduced['data']['i'])==minimum
    for role in ('forward','return'):
        for peak in reduced['selected'][role]['peaks']:
            assert reduced['data']['E'][peak['index']]==pytest.approx(peak['potential'])
