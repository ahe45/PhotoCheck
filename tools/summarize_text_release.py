"""Summarize the current packaged text-presence validation, without changing photos."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import statistics
import sys

sys.stdout.reconfigure(encoding='utf-8')
root = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root))
from photocheck.criteria import Criteria
from photocheck.domain import CRITERIA_VERSION

def report(name):
    return json.loads((root/'build'/name).read_text(encoding='utf-8'))

current = report('sample-frozen.json')
permissions = report('frozen-permissions.json')
smoke = report('isolated-smoke.json')
assert CRITERIA_VERSION == 'strict-0.9-text-runs-unvalidated'
assert current['criteria_versions'] == [CRITERIA_VERSION]
assert current['model_versions'] == ['mediapipe-0.10.21/google-float16-v1+ppocrv3-det+korean-ppocrv5-rec/face+text-ctc-runs-v1']
assert current['ok'] and current['frozen'] and current['originals_unchanged']
assert not current['analysis_exceptions'] and all(current['ui_checks'].values())
assert permissions['ok'] and permissions['frozen'] and not permissions['is_admin']
assert smoke['ok'] and smoke['frozen'] and smoke['settings_popup_save_and_result_snapshot']
with (root/'build/sample-frozen.csv').open(encoding='utf-8-sig', newline='') as handle:
    rows = list(csv.DictReader(handle))
assert len(rows) == current['total'] == current['processed']
assert {row['검사 설정 ID'] for row in rows} == {Criteria().identity}
assert all(json.loads(row['적용 검사 설정']) == Criteria().snapshot() for row in rows)
measured = [(row,json.loads(row['분석 수치'])) for row in rows]
text_rows = [(row,m) for row,m in measured if m.get('text_region_count',0)>0]
assert all(row['자동 분류']=='확인 필요' and '글자 포함 의심' in row['판정 사유'] for row,_ in text_rows)
sample = [(row,m) for row,m in measured if Path(row['파일 경로']).name=='71W298095.jpg']
assert len(sample)==1 and sample[0][0]['자동 분류']=='확인 필요'
assert '글자 포함 의심 — 좌측 하단 (1개 영역, 연속 3글자 이상)' in sample[0][0]['판정 사유']
assert sample[0][1]['text_score_max'] >= Criteria().text_confidence
assert sample[0][1]['text_run_max'] >= 3
assert all(m['text_run_max'] >= Criteria().text_min_chars and
           m['text_rec_score_max'] >= Criteria().text_rec_confidence for _,m in text_rows)
paper = [(row,m) for row,m in measured if Path(row['파일 경로']).name=='128100020.jpg']
assert len(paper)==1 and paper[0][0]['자동 분류']=='확인 필요'
assert paper[0][1].get('recapture_suspected')==1
times = [m['text_elapsed_ms'] for _,m in measured if 'text_elapsed_ms' in m]
with (root/'build/releases-0.8/sample-frozen.csv').open(encoding='utf-8-sig',newline='') as handle:
    previous_rows = list(csv.DictReader(handle))
previous_by_path = {row['파일 경로']:row for row in previous_rows}
assert set(previous_by_path) == {row['파일 경로'] for row in rows}
old_text = {row['파일 경로'] for row in previous_rows if '글자 포함 의심' in row['판정 사유']}
new_text = {row['파일 경로'] for row,_ in text_rows}
assert new_text <= old_text  # Same detector thresholds; recognition only filters candidates.
summary = {'criteria':Criteria().snapshot(), 'sample':sample[0],
    'text_candidate_photos':sum(m.get('text_candidate_count',0)>0 for _,m in measured),
    'previous_text_suspected':len(old_text), 'previous_candidates_filtered':len(old_text-new_text),
    'text_suspected':len(text_rows), 'text_regions':sum(m['text_region_count'] for _,m in text_rows),
    'text_average_ms':round(statistics.mean(times),3),
    'text_median_ms':round(statistics.median(times),3),
    'text_total_seconds':round(sum(times)/1000,2),
    'folders':dict(Counter(Path(row['상대 경로']).parts[0] for row in rows)),
    'accuracy_measured':False,
    'suspected_files':[{'file':row['상대 경로'],'reasons':row['판정 사유'], 'metrics':m} for row,m in text_rows]}
(root/'build/text-presence-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
exe = root/'dist/PhotoCheck.exe'
contents = exe.read_bytes()
compact = report('compact-archive.json')
assert compact['ok'] and compact['bytes'] == len(contents)
assert compact['sha256'] == hashlib.sha256(contents).hexdigest()
counts = current['counts']
checks = '\n'.join(f'- `{name}`: 통과' for name in permissions['checks'])
text = f'''# 사진 검수·배포 검증 결과

검증일: 2026-10-08. Windows 11 64비트, 관리자 권한 없는 계정. 기준 `{CRITERIA_VERSION}`, 기본 설정 ID `{Criteria().identity}`.

## 글자 존재 검사

사진 전체의 후보 영역만 PP-OCRv3/OpenCV로 찾고 후보에만 Korean PP-OCRv5/ONNX Runtime CPU 인식을 적용합니다. 검출 모델 2,423,490바이트, 인식 모델 13,418,787바이트, 사전 71,345바이트 및 라이선스를 단일 실행 파일에 포함합니다. 실행 중 다운로드·설치가 없으며 글자 내용은 화면·CSV·보고서에 저장하지 않습니다.

기본값은 **신뢰도 0.60 이상인 한글·영문·숫자가 최소 3개 연속된 경우**입니다. 공백·기호·낮은 신뢰도의 글자는 구간을 끊고 별도 영역의 글자 수는 합산하지 않습니다. 후보 검출은 영역 점수 0.60 이상, 영역 높이 / 사진 높이 0.8% 이상, 분석 사본 최대 길이 512px입니다. 인식용 영역 사본은 높이 48px, 너비 최대 640px입니다. 얼굴 점수와 별개이며 얼굴 미검출·여러 얼굴에서도 수행합니다. 주황색 상자와 목록 필터를 유지하며 톱니바퀴에서 최소 연속 글자 수·글자별 인식 신뢰도를 포함한 다섯 수치를 수정할 수 있습니다.

`71W298095.jpg`: **확인 필요 — 글자 포함 의심, 좌측 하단 1개 영역**. 영역 점수 {sample[0][1]['text_score_max']:.4f}, 연속 {sample[0][1]['text_run_max']}글자, 해당 구간의 최소 글자 신뢰도 {sample[0][1]['text_rec_score_max']:.4f}. 글자가 없는 얼굴·배경 및 니트 무늬 부분, 빈 배경은 대조 테스트에서 검출되지 않았습니다. 이 결과는 전체 표본의 오판정률을 의미하지 않습니다.

## 실제 샘플 전체 검사

- 현재 sample 폴더의 사진 {current['total']:,}장 처리: 정상 {counts.get('정상',0):,}, 확인 필요 {counts.get('확인 필요',0):,}, 파일 오류 {counts.get('파일 오류',0):,}.
- 후보가 있던 사진 {summary['text_candidate_photos']:,}장 중 연속 글자 기준 충족 {len(text_rows):,}장, 확정 의심 영역 {summary['text_regions']:,}개.
- 같은 파일 목록의 이전 글자 의심 {len(old_text):,}장 중 {len(old_text-new_text):,}장은 새 연속 글자·인식 신뢰도 기준을 충족하지 않아 글자 사유를 제외했습니다. 다른 검사 사유가 있으면 계속 확인 필요입니다. 이 차이는 오판정 개선율이 아닙니다.
- 전체 처리 {current['elapsed_seconds']:.2f}초. 글자 검출·후보 인식 단계 누적 {summary['text_total_seconds']:.2f}초, 사진당 평균 {summary['text_average_ms']:.3f}ms / 중앙값 {summary['text_median_ms']:.3f}ms. 최초 후보에서의 인식 모델 준비 시간도 글자 단계에 포함하며, 얼굴 모델 준비·파일 읽기·얼굴 분석·화면 처리 시간은 제외합니다.
- 검증 과정 전후 원본 SHA256 일치. 원본 사진을 수정하지 않았습니다.
- 분석 예외 {len(current['analysis_exceptions'])}건, 폴더 접근 오류 {len(current['discovery_issues'])}건. 미처리 0건.
- 화면 미리보기·이전/다음·검색·빈 필터 초기화 검증 통과. GUI 타이머 최대 간격 {current['gui_timer_max_delay_seconds']:.3f}초.
- 화면 프로세스 최대 메모리 {current['memory'].get('peak_mb')}MiB. 분석 자식 프로세스의 메모리는 이 값에 포함하지 않습니다.

샘플에는 정답 표시가 없어 정확도·오판정률을 산출하지 않았습니다. 작거나 흐린 글자가 인식되지 않아 빠지거나 무늬를 글자로 오인할 수 있으며 그림만 있는 로고는 대상이 아닙니다. 후보 영역만 인식하므로 전체 사진에 문자 인식을 추가하는 방식보다 작업 범위가 작습니다. 이번 측정은 특정 PC에서의 결과이며 처리 시간이 이전보다 짧았다는 사실만으로 성능 개선을 단정하지 않습니다.

## 테스트와 배포·권한

자동 테스트 **176개 통과**. 한글·영문·숫자 1~2글자 제외·3글자 포함, 반복 글자, 공백·기호, 글자별 신뢰도 0.60 경계, CTC 중복/빈 프레임, 별도 영역 합산 금지, 불량 모델 출력, 설정 저장·0.8 마이그레이션을 검증했습니다. 기존 파일·얼굴·GUI·필기체·무늬 대조 및 인식 신뢰도·최소 글자 수 저장 검사도 통과했습니다. 얼굴 높이 25%, 기울기 5도, 얼굴 점수 0.8, 환산 세로−가로 0.5~1.5 기준을 유지했습니다.

실행 파일은 {compact['previous_bytes']/1e6:.1f}MB → **{compact['bytes']/1e6:.1f}MB**, {compact['reduced_bytes']/1e6:.1f}MB ({compact['reduction_percent']:.2f}%) 감소했습니다. 새 글자 인식 모델과 실행 환경을 추가한 최종 용량입니다. 미사용 MediaPipe Solutions 모델·영상 FFmpeg·Qt PDF/QML/가상 키보드·AVIF·별도 ONNX C-API DLL을 제외했습니다. 남은 네이티브 파일 {compact['native_dependencies_checked']}개의 직접·지연 DLL 참조에 제거된 DLL이 없음을 검사했습니다. 필수 MediaPipe OpenCV DLL과 Qt 소프트웨어 그래픽 대체 기능은 유지했습니다.

실행 파일 하나만 새 한글/공백 폴더로 복사해 검증했습니다. 개발용 Python 경로를 제거하고 실행 폴더 쓰기를 차단했으며 기본 TEMP/TMP를 없는 경로로 설정했습니다. 사용자 LOCALAPPDATA의 런타임 폴더를 사용해 실행·모델 추론·검사를 완료했습니다. 모달 설정 저장과 결과 당시 설정 보존도 통과했습니다. 별도의 Python 미설치 실물 PC 및 Windows 10에서는 아직 검사하지 않았습니다.

Windows 실제 권한 검사 {len(permissions['checks'])}개 모두 통과:

{checks}

배포 파일 `dist/PhotoCheck.exe`: {len(contents):,}바이트. SHA256 `{hashlib.sha256(contents).hexdigest()}`.

## 결과 파일

- 전체 결과: `build/sample-frozen.json`, `build/sample-frozen.csv`
- 글자 검사 요약·의심 목록: `build/text-presence-summary.json`
- 권한 및 단일 파일 실행: `build/frozen-permissions.json`, `build/isolated-smoke.json`
- 실행 파일 축소와 DLL 의존성: `build/compact-archive.json`
- 실제 샘플 미리보기: `build/text-sample-preview.png`
- 설정 화면: `build/theme-settings-text.png`
- 이전 0.8 실행 파일과 보고서: `build/releases-0.8/`
'''
(root/'TEST_RESULTS.md').write_text(text,encoding='utf-8')
print(json.dumps({key:summary[key] for key in ('text_suspected','text_regions','text_average_ms','text_total_seconds')},ensure_ascii=False))
