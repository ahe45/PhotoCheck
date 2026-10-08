import csv
from dataclasses import replace
import json
from pathlib import Path
import numpy as np
from PIL import Image
import pytest

from photocheck.criteria import Criteria
from photocheck.domain import Status
from photocheck.files import inspect
from photocheck.process_analyzer import ProcessAnalyzer
from photocheck.recapture import detect_recapture

ROOT = Path(__file__).resolve().parent.parent


def sample_path(name):
    direct=ROOT/'sample'/name
    if direct.exists():
        return direct
    found=list((ROOT/'sample').rglob(name))
    return found[0] if len(found)==1 else direct


def baseline_metrics(name):
    with (ROOT/'build/sample-frozen-criteria-0.4.csv').open(encoding='utf-8-sig',newline='') as handle:
        return next(json.loads(r['분석 수치']) for r in csv.DictReader(handle) if r['상대 경로']==name)


@pytest.mark.parametrize('name,expected',[('128100020.jpg',1),('120200002.jpg',0),
    ('120801148.jpg',0),('127300486.jpg',0),('120200324.jpg',0),('120701537.jpg',0),
    ('122600034.jpg',0),('127300128.jpg',0),('127300247.jpg',0),('127703106.jpg',0),('127703141.jpg',0)])
def test_real_sample_paper_vs_portraits(name,expected):
    path=sample_path(name)
    if not path.exists():
        pytest.skip('local sample unavailable')
    with Image.open(path) as image:
        result=detect_recapture(np.array(image.convert('RGB')),baseline_metrics(name),Criteria())
    assert result['recapture_suspected']==expected


def test_full_image_border_and_flat_image_do_not_indicate_paper():
    metrics={'face_center_x':.5,'face_width_ratio':.3,'forehead_y_ratio':.3,'chin_y_ratio':.7}
    for rgb in (np.full((160,120,3),220,np.uint8),np.pad(np.full((156,116,3),220,np.uint8),((2,2),(2,2),(0,0)))):
        assert not detect_recapture(rgb,metrics,Criteria())['recapture_suspected']


def test_prefilter_skips_line_fitting_for_normal_portrait(monkeypatch):
    name='120200002.jpg'
    if not sample_path(name).exists():
        pytest.skip('local sample unavailable')
    def forbidden(*args,**kwargs):
        raise AssertionError('Noncandidate must not perform detailed fitting')
    monkeypatch.setattr('photocheck.recapture.cv2.HoughLinesP',forbidden)
    with Image.open(sample_path(name)) as image:
        assert not detect_recapture(np.array(image.convert('RGB')),baseline_metrics(name),Criteria())['recapture_candidate']


def test_real_spawned_engine_receives_custom_settings_and_recapture_toggle():
    path=sample_path('128100020.jpg')
    if not path.exists():
        pytest.skip('local sample unavailable')
    for c,expected in [(Criteria(),Status.REVIEW), (replace(Criteria(),check_recapture=False),Status.NORMAL),
                       (replace(Criteria(),check_recapture=False,face_height_min=.4),Status.REVIEW)]:
        analyzer=ProcessAnalyzer(criteria=c)
        try:
            result=inspect(path,path.parent,analyzer)
        finally:
            analyzer.close()
        assert result.status==expected, result.reasons
        assert result.criteria_settings==c.snapshot() and result.criteria_id==c.identity
        assert ('재촬영 의심' in result.tags)==c.check_recapture
