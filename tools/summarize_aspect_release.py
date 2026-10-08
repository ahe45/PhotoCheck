"""Compare the frozen aspect-ratio release, including relocated/new samples."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parent.parent


def report(name):
    return json.loads((root/'build'/name).read_text(encoding='utf-8'))


def rows(name):
    with (root/'build'/name).open(encoding='utf-8-sig',newline='') as handle:
        return {row['상대 경로']:row for row in csv.DictReader(handle)}


current=report('sample-frozen.json')
permissions=report('frozen-permissions.json')
smoke=report('isolated-smoke.json')
inventory=report('aspect-inventory.json')
old=rows('sample-frozen-criteria-0.5.csv')
new=rows('sample-frozen.csv')
assert current['ok'] and permissions['ok'] and smoke['ok']
assert current['criteria_versions']==['strict-0.6-aspect-ratio-unvalidated']
# The old photos were moved to a subdirectory. Unique basenames allow comparison
# while preserving the current relative paths in exported results.
by_name={Path(row['상대 경로']).name:row for row in new.values()}
assert len(by_name)==len(new), 'Cannot compare duplicate basenames'
assert set(old)<=set(by_name)
ratio_rows=[row for row in new.values() if '증명사진 비율 확인 필요' in row['판정 사유']]
expected={item['file'] for item in inventory['outside']}
assert {row['상대 경로'] for row in ratio_rows}==expected
assert all(row['자동 분류']=='확인 필요' for row in ratio_rows)
changed=[name for name,row in old.items() if row['자동 분류']!=by_name[name]['자동 분류']]
expected_changed=sorted(Path(name).name for name in expected if Path(name).name in old)
assert sorted(changed)==expected_changed
assert all(by_name[name]['자동 분류']=='확인 필요' for name in changed)
example=by_name['128100020.jpg']
assert example['자동 분류']=='확인 필요' and '재촬영 의심' in example['판정 사유']
settings_ids=sorted({row['검사 설정 ID'] for row in new.values()})
assert len(settings_ids)==1
assert all(json.loads(row['적용 검사 설정'])['check_aspect'] for row in new.values())
newly_added=[row for name,row in by_name.items() if name not in old]
comparison={'ok':True,'total':len(new),'baseline_total':len(old),'new_sample_count':len(newly_added),
    'current_counts':current['counts'],'baseline_photo_current_counts':dict(Counter(by_name[name]['자동 분류'] for name in old)),
    'new_sample_counts':dict(Counter(row['자동 분류'] for row in newly_added)),
    'aspect_count':len(ratio_rows),'aspect_files':[row['상대 경로'] for row in ratio_rows],
    'baseline_changed_files':changed,'settings_ids':settings_ids,'accuracy_measured':False,
    'elapsed_seconds':current['elapsed_seconds']}
(root/'build/aspect-release-comparison.json').write_text(json.dumps(comparison,ensure_ascii=False,indent=2),encoding='utf-8')
example_rows='\n'.join(f"| {row['상대 경로']} | {json.loads(row['분석 수치'])['image_width']}×{json.loads(row['분석 수치'])['image_height']} | {json.loads(row['분석 수치'])['image_aspect_ratio']:.4f} |" for row in ratio_rows)
exe=root/'dist/PhotoCheck.exe'
digest=hashlib.sha256(exe.read_bytes()).hexdigest().upper()
seconds=current['elapsed_seconds']
rounded_seconds=round(seconds)
document=f'''# 사진 검수·배포 검증 결과

검증일: 2026-10-08. Windows 11 64비트, 관리자 권한 없는 계정에서 최신 단일 실행 파일로 검사했습니다. 기준 버전 `strict-0.6-aspect-ratio-unvalidated`, 기본 설정 ID `{settings_ids[0]}`입니다.

## 전체 사진 비율 검사

전체 사진의 가로:세로 기본값 **3:4**, 기준 비율 대비 허용 오차 **±5%**를 적용합니다. EXIF 방향을 반영한 원래 표시 해상도의 가로÷세로가 **0.7125~0.7875** 밖이면 ‘사진 비율’ 사유로 확인 필요입니다. 경계값은 허용합니다. 축소 사본에서의 크기 반올림과 표시 수치 반올림으로 판정이 달라지지 않도록 원래 해상도의 교차 곱을 사용합니다.

3:4, 3.5:4.5와 픽셀 반올림으로 조금 달라지는 118×157·236×314는 기본값을 통과합니다. 정사각형, 가로형, 지나치게 넓거나 긴 사진은 확인 대상입니다. cm·DPI·특정 픽셀 해상도를 강제하지 않습니다. 3.5×4.5cm의 출처는 [외교부 여권 사진 규격](https://passport.go.kr/home/kor/contents.do?menuPos=32)이며, 이 앱의 기본값이 전체 여권 제출 규정을 검증하는 것은 아닙니다.

톱니바퀴 → 기본 검사 → **증명사진 가로·세로 비율**에서 검사 여부, 기준 가로·세로, 허용 오차를 수정합니다. ‘사진 비율’ 사유 필터와 실제 크기·비율·허용 범위를 포함하는 상세 사유를 제공합니다. 얼굴 높이 25%, 기울기 5도, 신뢰도 0.8, 기존 얼굴·재촬영 검사는 유지합니다. 비율 범위 안이라는 사실만으로 정상 분류하지 않습니다.

저장 설정은 다음 검사부터 적용하고 기존 결과의 기준은 유지합니다. 이전 0.5 설정은 다른 사용자 수치를 유지하고 새 비율 항목에 기본값을 추가하여 읽습니다. 로드 시 파일을 변경하지 않으며 다음 저장 때 최신 버전으로 기록합니다. CSV에 전체 적용 설정과 설정 ID, 사진 비율·기준 대비 편차 수치를 기록합니다.

## 최신 샘플 전체 검사

기존 14,111장은 하위 폴더로 이동되어 있었고 새 사진 {len(newly_added):,}장이 추가되어 전체 {len(new):,}장을 검사했습니다. 샘플에는 정답 표시가 없어 아래 수치는 정확도나 오판정률이 아닙니다.

| 항목 | 결과 |
|---|---:|
| 발견 / 처리 | {current['total']:,} / {current['processed']:,}장 |
| 정상 | {current['counts'].get('정상',0):,}장 |
| 확인 필요 | {current['counts'].get('확인 필요',0):,}장 |
| 파일 오류 | {current['counts'].get('파일 오류',0):,}장 |
| 비율 기준 밖 → 확인 필요 | {len(ratio_rows)}장 |
| 분석 예외 / 폴더 접근 오류 | {len(current['analysis_exceptions'])} / {len(current['discovery_issues'])}건 |
| 전체 검사 시간 | {seconds:.2f}초, 약 {rounded_seconds//60}분 {rounded_seconds%60}초 |
| 원본 보존 | 검사 전후 전체 SHA-256 일치 |
| 미리보기·이동·검색·빈 필터 | 모두 통과 |

기존 14,111장 중 비율 범위 밖인 {len(changed)}장이 정상에서 확인 필요로 바뀌고 나머지 분류는 유지됐습니다. 사용자 지정 재촬영 사례 `128100020.jpg`도 재촬영 의심으로 유지됐습니다. 추가 사진 {len(newly_added)}장의 결과는 `build/aspect-release-comparison.json`의 별도 집계에 기록했습니다. 샘플 수와 해상도 구성이 달라 이전 전체 시간과 직접적인 증가율 비교는 하지 않습니다. 이 검사는 이미지 크기 계산만 추가하며 새 모델 추론·원본 재읽기는 하지 않습니다.

화면 타이머 최대 간격 {current['gui_timer_max_delay_seconds']:.3f}초, 화면 프로세스 최대 메모리 {current['memory']['peak_mb']:.1f}MiB입니다. 별도 분석 프로세스는 포함하지 않습니다.

### 비율 범위 밖 사진

| 상대 경로 | EXIF 반영 해상도 | 가로/세로 |
|---|---:|---:|
{example_rows}

원본은 자르거나 회전해 저장하지 않습니다. 제출처에서 다른 비율을 허용하면 설정을 조정해야 합니다. 맞는 비율로 이미 잘린 재촬영은 비율 검사로 검출하지 못하며 별도 재촬영 검사의 한계도 유지됩니다.

## 검증

자동 테스트 **115개 모두 통과**했습니다. 기본 3:4·3.5:4.5, 정확한 ±5% 경계 통과, 경계 밖·정사각형·가로형·길쭉한 사진 분류, EXIF 90° 표시 방향, 축소 전 해상도, 검사 해제·사용자 비율·오차 변경, 얼굴 미검출에도 비율 사유 유지, 이전 설정 복원을 검증했습니다. 기존 파일·얼굴·재촬영·CSV·취소·분석 엔진 복구도 통과했습니다.

단일 실행 파일 하나를 한글·공백 경로의 읽기 전용 폴더에 복사하고, Python 환경변수·개발 경로를 제거하고, 기본 TEMP/TMP를 없는 경로로 지정한 환경에서 전체 검사를 통과했습니다. 배포 실행 검증에서 실제 설정 팝업 저장과 검사 당시 결과 보존도 확인했습니다. 관리자 권한 없이 접근 거부·읽기 전용·파일 잠금·설정 및 CSV 저장에 관한 **{len(permissions['checks'])}개 권한 검사 모두 통과**했습니다. 내장 Python DLL이 자체 해제 경로에서 로드됐습니다.

별도 Python 미설치 물리 PC와 Windows 10 직접 검증은 남아 있습니다. 사용자 로컬 데이터 폴더에는 쓰기 권한이 필요합니다.

## 파일

- 실행 파일: `dist/PhotoCheck.exe`, {exe.stat().st_size:,}바이트
- SHA-256: `{digest}`
- 전체 보고서와 CSV: `build/sample-frozen.json`, `build/sample-frozen.csv`
- 비율 검사 비교: `build/aspect-release-comparison.json`
- 원래 표시 크기 사전 조사: `build/aspect-inventory.json`
- 권한·기본 실행: `build/frozen-permissions.json`, `build/isolated-smoke.json`
- 설정 화면: `build/theme-settings-basic.png`
- 이전 0.5 결과 보존: `build/TEST_RESULTS-criteria-0.5.md`, `build/sample-frozen-criteria-0.5.json`과 CSV
'''
(root/'TEST_RESULTS.md').write_text(document,encoding='utf-8')
print(json.dumps(comparison,ensure_ascii=True,indent=2))
