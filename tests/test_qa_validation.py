"""QA metadata constraints and unit inference (M1–M9, M14, U6/U7)."""
import json
import pytest
from fastapi.testclient import TestClient
from benchcheck.app import app
from benchcheck.models import AnalysisConfig, ExperimentMetadata
from benchcheck.cv.analysis import analyze
from benchcheck.cv.parsing import parse_table
from tests.conftest import example_config


@pytest.mark.parametrize('field,value', [('temperature_c',-273.15), ('temperature_c',-300),
 ('ph',float('nan')), ('electrons_n',0), ('electrons_n',1.5), ('diffusion_coefficient_cm2_s',-1),
 ('electrode_area_cm2',0), ('active_mass_mg',-2), ('reference_electrode','banana'),
 ('scan_rate',{'value':1,'unit':None}), ('scan_rate',{'value':0,'unit':'mV/s'}),
 ('analyte_concentration',{'value':1,'unit':'bananas'}), ('notes','x'*501)])
def test_impossible_metadata_has_field_error(field,value):
    raw, base = example_config('synthetic_lmo_clear_return')
    cfg = base.model_dump()
    cfg['metadata'][field] = value
    response = TestClient(app).post('/api/analyze', files={'file':('x.csv',raw)},data={'config':json.dumps(cfg)})
    assert response.status_code == 422
    assert field in response.text
    assert 'math domain' not in response.text


@pytest.mark.parametrize('unit,factor', [('M',1),('mM',1e-3),('µM',1e-6),('uM',1e-6),('nM',1e-9)])
def test_concentration_units_validated(unit,factor):
    meta = ExperimentMetadata(analyte_concentration={'value':1,'unit':unit})
    assert meta.analyte_concentration.unit == unit


def test_header_units_inferred():
    raw,cfg = example_config('synthetic_lmo_clear_return')
    cfg.units = None
    result = analyze(parse_table(raw),cfg)
    assert '(mA)' in result['processing'][0]['detail']


@pytest.mark.parametrize('mapping',[{'potential':'E','current':'E'}, {'potential':'E','current':'I','time':'I'}])
def test_mapping_unique(mapping):
    with pytest.raises(ValueError, match='different columns'):
        AnalysisConfig(mapping=mapping)


@pytest.mark.parametrize('changes',[{'temperature_c':-273.15},{'from':'banana'}, {'offset_v':1}, {'target':'custom','offset_v':6}])
def test_preview_rejects_invalid(changes):
    response = TestClient(app).post('/api/conversion-preview',json={'from':'sce',**changes})
    assert response.status_code == 422


def test_unusual_metadata_warns():
    raw,cfg = example_config('synthetic_lmo_clear_return')
    cfg.metadata.temperature_c = 200
    assert any('temperature_c' in n for n in analyze(parse_table(raw),cfg)['notices'])
