from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
from PIL import Image
import pytest

from photocheck.criteria import Criteria, load_criteria
from photocheck.domain import Status
from photocheck.files import inspect
from photocheck.text_detection import MODEL_NAME, TextDetector, count_ctc_run, location, regions_from_map
from test_analysis import fixture_analyzer, run


def test_score_boundary_small_noise_and_normalized_locations():
    probability = np.zeros((100, 80), dtype=np.float32)
    probability[85:95, 4:24] = .5
    probability[3, 3] = 1  # isolated pixel cannot count as a text region
    regions = regions_from_map(probability, .5, .008)
    assert len(regions) == 1 and regions[0][1] == .5
    assert location(regions[0][0]) == '좌측 하단'
    assert regions_from_map(probability, .50001, .008) == []
    assert regions_from_map(probability, .5, .11) == []
    assert len(regions_from_map(probability, .5, .10)) == 1
    box = regions[0][0]
    assert all(0 <= value <= 1 for value in box)
    assert box[0]+box[2] <= 1 and box[1]+box[3] <= 1


@pytest.mark.parametrize('bad', [np.array([[np.nan]]), np.array([[np.inf]]),
                               np.array([[1.01]]), np.array([[-.01]]), np.zeros((0,0))])
def test_invalid_maps_raise_instead_of_passing(bad):
    with pytest.raises(ValueError):
        regions_from_map(bad, .6, .008)


def test_verified_text_is_reviewed_without_face_dependency():
    analyzer, _, _, _, responses = fixture_analyzer()
    calls = []
    box = (.05, .89, .2, .05)
    analyzer.text = NS(detect=lambda *args: (calls.append(args) or [(box, .95)], {'text_region_count':1}))
    result = run(analyzer)
    assert result.status == Status.REVIEW and '글자 포함 의심' in result.tags
    assert result.text_boxes == [box] and '좌측 하단' in result.reasons[0]
    responses[:] = [[]]
    result = run(analyzer)
    assert '글자 포함 의심' in result.tags and result.text_boxes == [box]
    assert len(calls) == 2
    analyzer.criteria = replace(Criteria(), check_text=False)
    run(analyzer)
    assert len(calls) == 2


def test_detection_failure_cannot_be_reported_as_normal(tmp_path):
    analyzer, *_ = fixture_analyzer()
    def fail(*args):
        raise RuntimeError('text model failed')
    analyzer.text = NS(detect=fail)
    path = tmp_path/'photo.png'
    Image.new('RGB', (300,400), 'white').save(path)
    result = inspect(path, tmp_path, analyzer)
    assert result.status == Status.REVIEW and '모델·분석' in result.tags


def test_previous_settings_keep_ratio_units_and_add_text_defaults(tmp_path):
    values = replace(Criteria(), aspect_tolerance=.25, roll_degrees=7).snapshot()
    values['version'] = 'strict-0.7-aspect-difference-unvalidated'
    for key in ('check_text', 'text_confidence', 'text_height_min', 'text_edge'):
        values.pop(key)
    path = tmp_path/'settings.json'
    path.write_text(json.dumps({'schema':1, 'criteria':values}), encoding='utf-8')
    before = path.read_bytes()
    criteria, error = load_criteria(path)
    assert not error and criteria.aspect_tolerance == .25 and criteria.roll_degrees == 7
    assert criteria.check_text and criteria.text_confidence == .6 and criteria.text_edge == 512
    assert path.read_bytes() == before


def test_settings_popup_persists_text_values_and_overlay_toggle(tmp_path):
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    from photocheck.settings_dialog import SettingsDialog
    from photocheck.ui import PhotoView
    from photocheck.domain import Result
    app = QApplication.instance() or QApplication([])
    dialog = SettingsDialog(Criteria(), path=tmp_path/'settings.json')
    dialog.fields['text_confidence'][0].setValue(.8)
    dialog.fields['text_height_min'][0].setValue(1.2)
    dialog.fields['text_edge'][0].setValue(768)
    dialog.fields['text_min_chars'][0].setValue(4)
    dialog.fields['text_rec_confidence'][0].setValue(.75)
    dialog.checks['check_text'].setChecked(False)
    assert not dialog.fields['text_edge'][0].isEnabled()
    dialog.save()
    saved, error = load_criteria(tmp_path/'settings.json')
    assert not error and not saved.check_text and saved.text_confidence == .8
    assert saved.text_height_min == .012 and saved.text_edge == 768
    assert saved.text_min_chars == 4 and saved.text_rec_confidence == .75
    view = PhotoView()
    image = QImage(300,400,QImage.Format.Format_RGB32)
    image.fill(0xffffffff)
    result = Result(tmp_path/'test.jpg', 'test.jpg', text_boxes=[(.05,.89,.2,.05)])
    view.display(image, result, True)
    assert len(view.overlay) == 1 and view.overlay[0].pen().color().name() == '#f59e0b'
    view.set_overlay(False)
    assert not view.overlay[0].isVisible()
    view.close()


def test_real_signature_and_text_free_crops():
    root = Path(__file__).resolve().parent.parent
    photos = list((root/'sample').rglob('71W298095.jpg'))
    model = root/'models'/MODEL_NAME
    if len(photos) != 1 or not model.exists():
        pytest.skip('Local sample and build-time model are required')
    detector = TextDetector(model.read_bytes())
    with Image.open(photos[0]) as source:
        rgb = np.array(source.convert('RGB'))
    regions, metrics = detector.detect(rgb, Criteria())
    assert len(regions) == 1 and location(regions[0][0]) == '좌측 하단'
    assert metrics['text_score_max'] >= Criteria().text_confidence
    assert metrics['text_run_max'] >= 3 and metrics['text_rec_score_max'] >= .6
    # Real face/background plus a knit-only crop, without modifying the source.
    for crop in (rgb[:800], rgb[600:830, 270:650], np.full((300,400,3),255,np.uint8)):
        assert detector.detect(crop, Criteria())[0] == []


@pytest.mark.parametrize('name', ['125100013.jpg','360212006.jpg','360212011.jpg',
                                '71W298020.jpg','125100395.jpg','120701218.jpg'])
def test_face_eyes_and_glasses_are_not_text(name):
    root = Path(__file__).resolve().parent.parent
    paths = list((root/'sample').rglob(name))
    model = root/'models'/MODEL_NAME
    if len(paths) != 1 or not model.exists():
        pytest.skip('Local negative sample/model required')
    detector = TextDetector(model.read_bytes())
    with Image.open(paths[0]) as source:
        assert detector.detect(np.array(source.convert('RGB')), Criteria())[0] == []


@pytest.mark.parametrize('origin', [(20,20),(90,180),(20,350)])
@pytest.mark.parametrize('background,foreground', [('white','black'),('black','white')])
def test_printed_korean_latin_presence_across_photo(origin,background,foreground):
    from PIL import ImageDraw, ImageFont
    root = Path(__file__).resolve().parent.parent
    font_path = Path('C:/Windows/Fonts/malgun.ttf')
    model = root/'models'/MODEL_NAME
    if not font_path.exists() or not model.exists():
        pytest.skip('Windows font/model required')
    detector = TextDetector(model.read_bytes())
    with Image.new('RGB', (300,400), background) as image:
        ImageDraw.Draw(image).text(origin, '검수 TEST', font=ImageFont.truetype(str(font_path),24), fill=foreground)
        regions, _ = detector.detect(np.array(image), Criteria())
        assert regions, (origin,background)
        x,y = origin
        assert any(bx < (x+120)/300 and bx+bw > x/300 and by < (y+36)/400 and by+bh > y/400
                   for (bx,by,bw,bh),_ in regions)


@pytest.mark.parametrize('text,expected', [('A',False),('AB',False),('ABC',True),
    ('AAA',True),('A B C',False),('AB-CD',False),('12',False),('123',True),
    ('가나',False),('가나다',True),('가 나 다',False)])
def test_real_recognizer_requires_three_consecutive_characters(text,expected):
    from PIL import ImageDraw, ImageFont
    root = Path(__file__).resolve().parent.parent
    font = Path('C:/Windows/Fonts/malgun.ttf')
    if not font.exists() or not (root/'models'/MODEL_NAME).exists():
        pytest.skip('Windows font and local models required')
    detector = TextDetector((root/'models'/MODEL_NAME).read_bytes())
    image = Image.new('RGB',(300,400),'white')
    ImageDraw.Draw(image).text((20,350),text,font=ImageFont.truetype(str(font),24),fill='black')
    regions,metrics = detector.detect(np.array(image), Criteria())
    assert bool(regions) == expected, (text, metrics)
    # A stricter saved count is respected, even for a valid three-letter run.
    if text == 'ABC':
        assert not detector.detect(np.array(image), replace(Criteria(), text_min_chars=4))[0]


def ctc(ids, scores=None):
    characters = ['', 'A', 'B', 'C', ' ', '-', '가', '나', '다']
    scores = scores or [.95]*len(ids)
    probability = np.full((len(ids),len(characters)),0.,np.float32)
    for row,index,score in zip(probability,ids,scores):
        row[:] = (1-score)/(len(characters)-1)
        row[index] = score
    return probability, characters


@pytest.mark.parametrize('ids,scores,count', [
    ([1,1,2,2,3],None,3), ([1,1,1],None,1),
    ([1,0,1,0,1],None,3), ([1,4,2,4,3],None,1),
    ([1,2,5,3],None,2), ([1,2,3],[.9,.59,.9],1),
    ([1,2,3],[.9,.6,.9],3), ([6,7,8],None,3),
])
def test_ctc_repeats_blank_separators_and_confidence_boundary(ids,scores,count):
    probability,characters = ctc(ids,scores)
    length,confidence = count_ctc_run(probability,characters,.6)
    assert length == count
    assert confidence >= .6


def test_separate_regions_are_not_added_together(monkeypatch):
    detector = object.__new__(TextDetector)
    detector.mean,detector.std = np.zeros(3),np.ones(3)
    detector.net = NS(setInput=lambda *a:None,forward=lambda:np.zeros((32,32),np.float32))
    monkeypatch.setattr('photocheck.text_detection.regions_from_map',
                        lambda *a:[((.1,.1,.1,.05),.9),((.4,.1,.1,.05),.9)])
    detector.recognize_run = lambda *a:(2,.9)
    regions,metrics = detector.detect(np.zeros((100,100,3),np.uint8),Criteria())
    assert regions == [] and metrics['text_candidate_count'] == 2 and metrics['text_run_max'] == 2


def test_prior_text_settings_migrate_without_rewriting(tmp_path):
    values = replace(Criteria(),text_confidence=.75,roll_degrees=8).snapshot()
    values['version'] = 'strict-0.8-text-presence-unvalidated'
    values.pop('text_min_chars'); values.pop('text_rec_confidence')
    path=tmp_path/'settings.json'
    path.write_text(json.dumps({'schema':1,'criteria':values}),encoding='utf-8')
    before=path.read_bytes()
    criteria,error = load_criteria(path)
    assert not error and criteria.text_min_chars == 3 and criteria.text_rec_confidence == .6
    assert criteria.text_confidence == .75 and criteria.roll_degrees == 8
    assert path.read_bytes() == before


@pytest.mark.parametrize('count',[2,3.5,True,float('nan')])
def test_invalid_minimum_character_count(count):
    with pytest.raises(ValueError):
        replace(Criteria(),text_min_chars=count)


@pytest.mark.parametrize('bad',[np.zeros((1,9)),np.full((1,9),np.nan),np.ones((2,3)),np.zeros((0,9))])
def test_invalid_recognition_output_cannot_pass(bad):
    with pytest.raises(ValueError):
        count_ctc_run(bad,ctc([1])[1],.6)
