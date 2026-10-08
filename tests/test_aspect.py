from dataclasses import replace

from PIL import Image
import pytest

from photocheck.criteria import Criteria
from photocheck.domain import Check, Status
from photocheck.files import inspect
from test_analysis import fixture_analyzer, run


@pytest.mark.parametrize('size,flag', [
    ((300,400),False), ((350,450),False), ((118,157),False), ((236,314),False),
    ((600,700),False), ((200,300),False),  # normalized differences .5 and 1.5
    ((600,699),True), ((200,301),True),
    ((300,300),True), ((400,300),True), ((200,400),True), ((400,500),False),
])
def test_default_ratio_and_inclusive_boundaries(size,flag):
    analyzer,*_=fixture_analyzer()
    result=run(analyzer,size)
    assert ('사진 비율' in result.tags)==flag
    assert any(r.startswith('증명사진 비율 확인 필요') for r in result.reasons)==flag
    assert result.metrics['image_aspect_ratio']==pytest.approx(size[0]/size[1],abs=1e-6)
    if flag:
        assert result.status==Status.REVIEW and result.framing_check==Check.REVIEW


def test_ratio_uses_original_resolution_before_thumbnail_rounding():
    analyzer,*_=fixture_analyzer()
    result=run(analyzer,metrics={'image_width':200,'image_height':301})
    assert '사진 비율' in result.tags
    assert result.metrics['aspect_difference']==1.515


def test_exif_rotated_original_dimensions_are_used(tmp_path):
    analyzer,*_=fixture_analyzer()
    path=tmp_path/'가로저장_세로표시.jpg'
    exif=Image.Exif()
    exif[274]=6
    with Image.new('RGB',(400,300),'white') as image:
        image.save(path,exif=exif)
    result=inspect(path,tmp_path,analyzer)
    assert (result.metrics['image_width'],result.metrics['image_height'])==(300,400)
    assert '사진 비율' not in result.tags and result.status==Status.NORMAL


@pytest.mark.parametrize('criteria',[replace(Criteria(),check_aspect=False),
                                    replace(Criteria(),aspect_width=1,aspect_height=1)])
def test_disable_or_custom_ratio_allows_square(criteria):
    analyzer,*_=fixture_analyzer()
    analyzer.criteria=criteria
    result=run(analyzer,(300,300))
    assert result.status==Status.NORMAL and '사진 비율' not in result.tags
    assert result.criteria_settings==criteria.snapshot()


def test_custom_tolerance_and_zero_tolerance():
    analyzer,*_=fixture_analyzer()
    analyzer.criteria=replace(Criteria(),aspect_tolerance=.25)
    assert '사진 비율' not in run(analyzer,(400,500)).tags  # difference=.75, inclusive
    assert '사진 비율' in run(analyzer,(400,499)).tags
    analyzer.criteria=replace(Criteria(),aspect_tolerance=0)
    assert '사진 비율' not in run(analyzer,(300,400)).tags
    assert '사진 비율' in run(analyzer,(300,401)).tags


@pytest.mark.parametrize('size',[(300,350),(600,700),(1200,1400)])
def test_same_shape_same_normalized_difference_regardless_of_pixels(size):
    analyzer,*_=fixture_analyzer()
    result=run(analyzer,size)
    assert result.metrics['aspect_difference']==.5 and '사진 비율' not in result.tags


@pytest.mark.parametrize('size,flag', [((600,750),False),((600,850),False),
                                     ((600,749),True),((600,851),True)])
def test_custom_base_width_and_height_use_their_own_ratio_units(size,flag):
    analyzer,*_=fixture_analyzer()
    analyzer.criteria=replace(Criteria(),aspect_width=6,aspect_height=8,aspect_tolerance=.5)
    result=run(analyzer,size)
    assert ('사진 비율' in result.tags)==flag
    assert result.metrics['aspect_target_difference']==2


def test_ratio_reason_survives_face_not_found():
    analyzer,_,_,_,responses=fixture_analyzer()
    responses[:]=[[],[]]
    result=run(analyzer,(300,300))
    assert '사진 비율' in result.tags and '얼굴·신뢰도' in result.tags
