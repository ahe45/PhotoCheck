"""Summarize the completed frozen scan; retain previous baseline reports."""
import csv
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent


def load(name):
    return json.loads((root/'build'/name).read_text(encoding='utf-8'))


def rows(name):
    with (root/'build'/name).open(encoding='utf-8-sig',newline='') as handle:
        return {r['상대 경로']:r for r in csv.DictReader(handle)}


current, previous = load('sample-frozen.json'),load('sample-frozen-criteria-0.4.json')
permissions = load('frozen-permissions.json')
timing = load('recapture-fast-validation.json')
smoke = load('isolated-smoke.json')
new, old = rows('sample-frozen.csv'),rows('sample-frozen-criteria-0.4.csv')
assert current['ok'] and current['frozen'] and permissions['ok'] and smoke['ok']
assert set(new)==set(old)
assert current['criteria_versions']==['strict-0.5-settings-recapture-unvalidated']
changed = [n for n in new if new[n]['자동 분류']!=old[n]['자동 분류']]
assert changed == ['128100020.jpg'], changed
assert all(json.loads(r['적용 검사 설정'])['check_recapture'] for r in new.values())
settings_ids = sorted({r['검사 설정 ID'] for r in new.values()})
assert len(settings_ids)==1 and settings_ids[0]
example = new['128100020.jpg']
metrics = json.loads(example['분석 수치'])
assert metrics['recapture_suspected']==1
recapture = [n for n,r in new.items() if '재촬영 의심' in r['판정 사유']]
assert recapture==['128100020.jpg']
seconds = current['elapsed_seconds']
delta = seconds-previous['elapsed_seconds']
percent = delta/previous['elapsed_seconds']*100
comparison = {'ok':True,'total':len(new),'previous_counts':previous['counts'],
    'current_counts':current['counts'],'changed_files':changed,'recapture_files':recapture,
    'baseline_seconds':previous['elapsed_seconds'],'current_seconds':seconds,
    'delta_seconds':round(delta,2),'delta_percent':round(percent,2),
    'settings_ids':settings_ids,'example':{'file':'128100020.jpg','status':example['자동 분류'],
        'reasons':example['판정 사유'],'metrics':metrics},'accuracy_measured':False}
(root/'build/recapture-release-comparison.json').write_text(json.dumps(comparison,ensure_ascii=False,indent=2),encoding='utf-8')
exe=root/'dist/PhotoCheck.exe'
digest=hashlib.sha256(exe.read_bytes()).hexdigest().upper()
labels = {
    'unreadable_file_is_error':'읽기 금지 사진을 파일 오류로 처리',
    'unreadable_subfolder_reported':'접근 금지 하위 폴더 안내',
    'unwritable_export_rejected':'저장 금지 폴더의 CSV 저장 실패 처리',
    'unwritable_settings_rejected':'저장 금지 폴더의 설정 저장 실패 처리',
    'writable_settings_roundtrip':'설정 저장·다시 읽기',
    'readonly_settings_preserved':'읽기 전용 설정 파일의 기존 내용 보존',
    'readonly_csv_preserved':'읽기 전용 CSV의 기존 내용 보존',
    'locked_csv_rejected':'다른 프로그램이 잠근 CSV 저장 실패 처리',
    'analysis_without_admin':'관리자 권한 없는 실제 모델 분석',
    'original_preserved':'원본 내용 보존',
    'writable_export_succeeds':'쓰기 가능한 위치에 CSV 저장',
    'no_orphan_export_temporary':'임시 CSV 잔여 파일 없음',
    'no_orphan_settings_temporary':'임시 설정 잔여 파일 없음',
}
checks='\n'.join(f'| {labels[name]} | {"통과" if ok else "실패"} |' for name,ok in permissions['checks'].items())
document=f'''# 사진 검수·배포 검증 결과

검증일: 2026-10-08. Windows 11 64비트, 관리자 권한 없는 계정에서 최신 단일 실행 파일 `dist/PhotoCheck.exe`로 검사했습니다. 기준 버전은 `strict-0.5-settings-recapture-unvalidated`, 기본 설정 ID는 `{settings_ids[0]}`입니다.

## 이번 변경

오른쪽 위 톱니바퀴 아이콘을 눌러 기본 검사·정면 검사·재촬영 검사 팝업을 엽니다. 선택 검사 켜기·끄기와 기준값 수정, 저장·취소·기본값 복원을 제공합니다. 기본값은 얼굴 높이 25%, 기울기 5도, 신뢰도 0.8입니다. 저장한 설정은 `%LOCALAPPDATA%\\PhotoCheck\\settings.json`에 기록되며 다음 검사부터 적용합니다. 진행 중 설정 변경은 막고 기존 결과의 설정은 유지합니다. CSV에 적용 설정 전체와 설정 ID를 기록합니다.

파일 유효성, 얼굴 미검출·여러 얼굴, 분석 오류·특징점 충돌은 항상 확인합니다. 정방향 얼굴 미검출 시에만 180°로 검출합니다. 얼굴 높이 기준 이하, 기울기 절댓값 기준 이상, 신뢰도 기준 이하를 확인 대상으로 처리합니다. 정면·중앙 위치·얼굴 특징점 경계 여백 조건도 기본적으로 켜져 있습니다. 어깨·가슴은 요구하지 않습니다.

## 전체 샘플 검사

정답 표시가 없는 JPEG 14,111장, 총 407,225,877바이트를 처리했습니다. 수치는 자동 분류 결과이며 정확도나 오판정률을 뜻하지 않습니다.

| 항목 | 결과 |
|---|---:|
| 발견 / 처리 | {current['total']:,} / {current['processed']:,}장 |
| 정상 | {current['counts'].get('정상',0):,}장 |
| 확인 필요 | {current['counts'].get('확인 필요',0):,}장 |
| 파일 오류 | {current['counts'].get('파일 오류',0):,}장 |
| 분석 예외 / 폴더 접근 오류 | {len(current['analysis_exceptions'])} / {len(current['discovery_issues'])}건 |
| 전체 처리 시간 | {seconds:.2f}초 |
| 이전 전체 처리 시간 | {previous['elapsed_seconds']:.2f}초 |
| 증가 | {delta:.2f}초 ({percent:.2f}%) |
| 원본 SHA-256 보존 | {'전체 일치' if current['originals_unchanged'] else '실패'} |
| 미리보기·이동·검색·빈 필터 처리 | 모두 통과 |

이전 정상 14,087장·확인 필요 24장에서 정상 {current['counts'].get('정상',0):,}장·확인 필요 {current['counts'].get('확인 필요',0):,}장으로 바뀌었습니다. 분류가 달라진 사진은 사용자 지정 재촬영 사례 `128100020.jpg` 한 장입니다. 나머지 14,110장의 분류는 유지됐습니다.

화면 타이머의 최대 간격은 {current['gui_timer_max_delay_seconds']:.3f}초, 화면 프로세스 최대 메모리는 {current['memory']['peak_mb']:.1f}MiB입니다. 별도 분석 프로세스 메모리는 포함하지 않습니다. 처리 시간은 동일 PC에서의 각각 한 번의 실행 비교이며 PC 부하에 따라 달라질 수 있습니다.

최신 결과: `build/sample-frozen.json`, `build/sample-frozen.csv`. 이전 결과는 `build/sample-frozen-criteria-0.4.json`과 같은 이름의 CSV에 보존했습니다. 비교 결과는 `build/recapture-release-comparison.json`입니다.

## 재촬영 검사와 확인된 사례

이미 디코딩한 RGB 사본을 재사용하고 최대 384px에서 빠른 테두리 후보 검사를 합니다. 후보만 상세 직선 결합을 수행합니다. 얼굴을 둘러싼 테두리 3면, 두 면의 안팎 색 차이, 종이 밖 배경 명암 변화를 함께 요구합니다. 이미지 자체의 가장자리와 단일 옷·머리 선만으로 통과시키지 않습니다. 추가 신경망 추론이나 원본 재읽기는 없습니다.

기본값: 종이 면적 15~85%, 최소 테두리 길이 사진 너비의 25%, 안팎 색 차이 3, 바깥 배경 명암 변화 12. 색 차이는 RGB 채널 중앙값 차이 중 최댓값이며 명암 변화는 외부 회색조의 90백분위−10백분위입니다. 두 값 모두 0~255 범위입니다.

읽기 전용 사전 전수 검사에서 빠른 후보는 {timing['candidate_count']}장({timing['candidate_count']/timing['total']:.2%}), 최종 의심은 {timing['suspected_count']}장이었습니다. 재촬영 계산 합계는 {timing['detector_seconds']:.3f}초였으며, 별도 이미지 읽기 시간은 이 값에 포함하지 않습니다. 보고서는 `build/recapture-fast-validation.json`, 재현 도구는 `tools/validate_recapture.py`입니다. 이전 반복 윤곽 실험의 추가 계산 107.79초보다 줄었으며, 최신 통합 앱 시간은 위 표에 별도로 기록했습니다.

`128100020.jpg`(118×157px)는 얼굴 높이 약 {metrics['face_height_ratio']:.2%}, 기울기 {metrics['roll_degrees']:.2f}°, 신뢰도 {metrics['face_confidence']:.4f}로 기존 얼굴 조건은 통과합니다. 새 검사에서는 종이 면적 {metrics['paper_area_ratio']:.2%}, 상단·측면 색 차이 {metrics['paper_top_contrast']:g}·{metrics['paper_side_contrast']:g}, 외부 배경 명암 변화 {metrics['paper_background_spread']:g}가 기록되고 ‘인화사진 재촬영 의심 — 얼굴 주변의 종이 테두리·외부 배경 확인’으로 확인 필요가 됩니다.

흰 테두리·사진관 편집 배경이 보이는 추가 후보 7장을 직접 살펴보고 외부 배경 명암 조건을 보완했습니다. `120200324.jpg`, `120701537.jpg`, `122600034.jpg`, `127300128.jpg`, `127300247.jpg`, `127703106.jpg`, `127703141.jpg`는 기본 설정에서 재촬영으로 잡히지 않습니다. 일반 비교 사진 `120200002.jpg`, `120801148.jpg`, `127300486.jpg`도 후보 단계에서 제외됩니다. 이것은 확인한 사례의 동작이며 재촬영 성공률 평가가 아닙니다.

한계: 테두리가 잘림, 균일한 외부 배경, 약한 선, 종이 기울기, 편집으로 만든 테두리·명암 패턴 등에서 누락 또는 오검출이 가능합니다. 재촬영 확정이나 위변조 증명이 아닌 확인 대상 제시입니다. 정답을 붙인 다양한 원본·재촬영 사진에서 별도 성능 평가가 필요합니다.

## 설정·화면·자동 테스트

자동 테스트 **96개 모두 통과**했습니다. 기존 파일·EXIF·회전·판정 경계·CSV·취소·분석 프로세스 복구 외에 실제 샘플 재촬영 검사, 일반 테두리 사진 제외, 비후보 상세 검사 생략, 실제 별도 모델 프로세스의 사용자 기준 반영을 검사했습니다.

설정 저장·재로드, 취소, 기본값 복원, 잘못된 수치·최솟값/최댓값 거부, 손상 설정 안내·기본값 적용, 저장 실패 시 기존 설정 보존, CSV의 검사 당시 설정 보존을 확인했습니다. 배포 EXE 기본 실행 검증에서 실제 톱니바퀴 팝업을 열어 수치를 저장하고 검사 당시 결과가 변하지 않는 것도 확인했습니다.

밝은 테마의 팝업 3개 탭을 렌더링해 확인했습니다. 미리보기는 `build/theme-settings-basic.png`, `build/theme-settings-front.png`, `build/theme-settings-recapture.png`입니다. 최신 EXE 실행 증거는 `build/isolated-smoke.json`입니다.

## Python 설치 의존성·권한

실행 파일 하나만 프로젝트 밖의 한글·공백 폴더에 복사했습니다. PATH는 Windows System32만 남기고 PYTHON 환경변수를 제거했습니다. 실행 폴더에 실제 쓰기 거부를 적용하고 기본 TEMP/TMP는 없는 경로로 지정했습니다. 이 환경에서 전체 검사와 UI 검증이 통과했습니다. 임시 리소스는 사용자 로컬 데이터에 풀리고 내장 Python DLL을 사용합니다. 설정 파일도 실행 폴더 쓰기를 요구하지 않습니다.

실제 접근 거부·읽기 전용·잠금 검사는 새 임시 사본에만 수행하고 권한을 복구했습니다. 관리자 권한 없이 {len(permissions['checks'])}항목을 통과했습니다. 진단용 파일 생성 단계에서는 쓰기 가능한 TEMP를 사용했습니다.

| 검증 항목 | 결과 |
|---|---|
{checks}

권한 보고서: `build/frozen-permissions.json`. 별도의 Python 미설치 물리 PC와 Windows 10 직접 검증은 하지 못했습니다. 위 결과는 Windows 11에서 개발 환경 경로 제거와 내장 실행 환경을 확인한 것입니다. 사용자 로컬 데이터 폴더에는 쓰기 권한이 필요합니다.

## 배포 파일

`dist/PhotoCheck.exe` 하나를 복사해 실행합니다. 크기 {exe.stat().st_size:,}바이트. SHA-256: `{digest}`.

기존 개발 실험과 기준 0.4 보고서는 `build/TEST_RESULTS-criteria-0.4.md`에 보존했습니다.
'''
(root/'TEST_RESULTS.md').write_text(document,encoding='utf-8')
print(json.dumps({k:comparison[k] for k in ('ok','total','current_counts','changed_files','current_seconds','delta_seconds','delta_percent')},ensure_ascii=True))
