import json
import pytest
from fastapi.testclient import TestClient
from benchcheck.app import app
from benchcheck.evidence.serpapi import validate_public_url
from benchcheck.reasoning.report import _md_escape, _safe_url
from tests.conftest import example_config


def analysis(client):
    raw,cfg=example_config('synthetic_lmo_clear_return')
    return client.post('/api/analyze',files={'file':('x.csv',raw)},data={'config':cfg.model_dump_json()}).json()


def test_host_head_headers_and_request_limit():
    client=TestClient(app)
    assert client.get('/',headers={'host':'attacker.example'}).status_code==400
    response=client.head('/')
    assert response.status_code==200 and not response.content
    assert response.headers['x-content-type-options']=='nosniff'
    assert 'frame-ancestors' in response.headers['content-security-policy']
    assert client.post('/api/inspect',headers={'content-length':str(31*1024*1024)},content=b'').status_code==413
    assert client.post('/api/report',content=b'x'*(1024*1024+1)).status_code==413


def test_duplicate_file_parts():
    assert TestClient(app).post('/api/inspect',files=[('file',('a.csv',b'a,b')),('file',('b.csv',b'a,b'))]).status_code==422


@pytest.mark.parametrize('url',['http://127.0.0.1/','http://169.254.169.254/','http://[::1]/','http://192.168.1.1/','file:///tmp/a','http://localhost/'])
def test_private_extract_targets_rejected(url):
    with pytest.raises(ValueError,match='public'):
        validate_public_url(url,resolve=False)


def test_markdown_escapes_markup_and_link_syntax():
    escaped=_md_escape('<img onerror=bad> [x](javascript:bad)\x00\u202e')
    assert '<' not in escaped and '\\]' in escaped and '\\)' in escaped
    assert '\x00' not in escaped and '\u202e' not in escaped
    assert _safe_url(' JavaScript:alert(1) ') is None
    assert _safe_url(' HTTPS://example.org/a ')=='HTTPS://example.org/a'


def test_report_requires_server_analysis_and_ignores_forged_provenance():
    client=TestClient(app)
    a=analysis(client)
    changed={**a,'example_id':None,'observations':[{'text':'FAKE'}]}
    changed.pop('data')
    r=client.post('/api/report',json={'analysis':changed,'evidence':{'sources':[{'source_id':'fake','applicability':{'level':'condition-matched'}}]}})
    assert r.status_code==200
    assert 'FAKE' not in r.text and r.json()['synthetic']
    assert client.post('/api/report',json={'analysis':{}}).status_code==422


def test_evidence_session_and_source_validation():
    client=TestClient(app)
    a=analysis(client)
    ctx={'metadata':a['metadata']}
    for sources in ([{}],[{'source_id':'fake','title':None}],[{'source_id':'fake','title':'made up','link':'http://127.0.0.1'}]):
        assert client.post('/api/evidence/select',json={'analysis_id':a['analysis_id'],'sources':sources,'context':ctx}).status_code==422
    for query in (' ', 'x'*301):
        assert client.post('/api/evidence/search',json={'analysis_id':a['analysis_id'],'query':'','query_id':'q','context':ctx}).status_code==422


def test_finite_conversion_errors_do_not_serialize_nan():
    client=TestClient(app,raise_server_exceptions=False)
    for value in ('NaN','Infinity','-Infinity'):
        response=client.post('/api/conversion-preview',content='{"from":"sce","ph":'+value+'}',headers={'content-type':'application/json'})
        assert response.status_code==422 and 'ph' in response.text


def test_request_file_limit_remains_413():
    response=TestClient(app).post('/api/inspect',files={'file':('large.csv',b'0'*(25*1024*1024+1))})
    assert response.status_code==413
