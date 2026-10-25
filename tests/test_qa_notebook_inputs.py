"""Replay notebook upload/metadata/malformed-source inputs locally, without live requests.

The original notebook remains unchanged. Invalid inputs may stop a print-only
reproduction at a missing result key after the expected 422; every HTTP response
is independently checked here, with behavior assertions in the focused QA tests.
"""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from benchcheck.app import app

CASES=[*range(6,28,2),*range(31,49,2),51,53,55,57,59,61,100,102]

@pytest.mark.parametrize('case',CASES)
def test_notebook_inputs_never_500(case):
    client=TestClient(app,raise_server_exceptions=False)
    responses=[]
    def request(method,url,**kwargs):
        response=client.request(method,url.removeprefix('http://127.0.0.1:8000'),**kwargs)
        responses.append(response)
        assert response.status_code<500, response.text[:500]
        return response
    namespace={'requests':SimpleNamespace(post=lambda url,**kw:request('POST',url,**kw),get=lambda url,**kw:request('GET',url,**kw),head=lambda url,**kw:request('HEAD',url,**kw)), 'print':lambda *a,**k:None}
    directory=Path(__file__).parent/'qa_cases'
    for setup in (4,29):
        exec((directory/f'input_{setup}.py').read_text(),namespace)
    try:
        exec((directory/f'input_{case}.py').read_text(),namespace)
    except (KeyError,TypeError,IndexError):
        assert responses
        if case == 22:
            assert responses[-1].json()["suggested"]["current"] is None
        else:
            assert responses[-1].status_code==422
    except json.JSONDecodeError:
        assert case == 51 and responses[-1].status_code == 400
    assert responses
