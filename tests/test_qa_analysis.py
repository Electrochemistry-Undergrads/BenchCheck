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
