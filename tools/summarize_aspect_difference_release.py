"""Compare the new ratio-difference rule with the archived percentage scan."""
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
old=rows('sample-frozen-criteria-0.6.csv')
new=rows('sample-frozen.csv')
assert current['ok'] and permissions['ok'] and smoke['ok'] and current['originals_unchanged']
assert current['criteria_versions']==['strict-0.7-aspect-difference-unvalidated']
assert set(old)==set(new)
ratio_rows=[row for row in new.values() if '증명사진 비율 확인 필요' in row['판정 사유']]
expected={item['file'] for item in inventory['outside']}
assert {row['상대 경로'] for row in ratio_rows}==expected
assert all(row['자동 분류']=='확인 필요' for row in ratio_rows)
changed=[]
for name,row in old.items():
    previous_reasons=[r for r in row['판정 사유'].split(' | ') if r]
    other_reasons=[r for r in previous_reasons if not r.startswith('증명사진 비율 확인 필요')]
    prediction='확인 필요' if name in expected or other_reasons else '정상'
    if row['자동 분류']=='파일 오류':
        prediction='파일 오류'
    assert new[name]['자동 분류']==prediction, (name,prediction,new[name]['자동 분류'])
    if row['자동 분류']!=new[name]['자동 분류']:
        changed.append({'file':name,'before':row['자동 분류'],'after':new[name]['자동 분류']})
settings_ids=sorted({row['검사 설정 ID'] for row in new.values()})
assert len(settings_ids)==1
assert all(json.loads(row['적용 검사 설정'])['aspect_tolerance']==.5 for row in new.values())
recaptured=next(row for row in new.values() if Path(row['상대 경로']).name=='128100020.jpg')
assert '재촬영 의심' in recaptured['판정 사유'] and recaptured['자동 분류']=='확인 필요'
comparison={'ok':True,'total':len(new),'counts':current['counts'],
    'previous_counts':dict(Counter(row['자동 분류'] for row in old.values())),
    'aspect_count':len(ratio_rows),'aspect_files':[row['상대 경로'] for row in ratio_rows],
    'changed_files':changed,'settings_ids':settings_ids,'elapsed_seconds':current['elapsed_seconds'],
    'accuracy_measured':False}
(root/'build/aspect-difference-comparison.json').write_text(json.dumps(comparison,ensure_ascii=False,indent=2),encoding='utf-8')
exe=root/'dist/PhotoCheck.exe'
digest=hashlib.sha256(exe.read_bytes()).hexdigest().upper()
seconds=current['elapsed_seconds']
rounded=round(seconds)
examples='\n'.join(f"| {row['상대 경로']} | {json.loads(row['분석 수치'])['image_width']}×{json.loads(row['분석 수치'])['image_height']} | {json.loads(row['분석 수치'])['aspect_difference']:.6f} |" for row in ratio_rows)
document=f'''# 사진 검수·배포 검증 결과

검증일: 2026-10-08. Windows 11 64비트, 관리자 권한 없는 계정에서 최신 단일 실행 파일로 검사했습니다. 기준 버전 `strict-0.7-aspect-difference-unvalidated`, 기본 설정 ID `{settings_ids[0]}`입니다.

## 변경한 비율 계산과 화면

기준 가로:세로 **3:4**, **허용 오차 비율 0.5**를 기본값으로 적용합니다. 실제 사진의 가로를 기준 가로 3에 맞춰 환산한 뒤 **환산 세로−가로**를 계산합니다. 기준 차이 4−3=1을 중심으로 **0.5~1.5**를 허용하며 양쪽 경계값도 통과합니다. 이는 가로 3일 때 세로 3.5~4.5에 해당합니다. 백분율 방식은 대체됐습니다.

일반식: 기준 가로 A, 기준 세로 B, 오차 E, 사진 너비 W, 높이 H에 대해 환산 차이는 `A×H/W−A`입니다. `(B−A)−E ≤ A×H/W−A ≤ (B−A)+E`이면 이 검사를 통과합니다. 판정은 원래 EXIF 반영 해상도의 정확한 교차 곱으로 비교하고 표시 수치 반올림은 판단에 사용하지 않습니다. 300×350과 600×700은 동일한 모양이므로 같은 차이 0.5로 통과합니다.

| 실제 사진 크기 | 가로 3 기준 환산 | 세로−가로 | 비율 검사 |
|---|---|---:|---|
| 300×400 | 3:4 | 1 | 통과 |
| 300×350 | 3:3.5 | 0.5 | 통과, 경계 포함 |
| 200×300 | 3:4.5 | 1.5 | 통과, 경계 포함 |
| 600×699 | 3:3.495 | 0.495 | 확인 필요 |
| 200×301 | 3:4.515 | 1.515 | 확인 필요 |
| 300×300 | 3:3 | 0 | 확인 필요 |

톱니바퀴 → 기본 검사의 라벨은 **허용 오차 비율**로 바꾸고 설명에도 가로 환산, 세로−가로 비교, 0.5~1.5 예시와 경계 통과를 반영했습니다. 상세 사유와 CSV에는 환산 차이·기준 차이·차이 오차를 기록합니다. 새 설정은 다음 검사부터 적용하고 기존 결과의 당시 설정은 유지합니다.

이전 0.5·0.6 저장 설정의 검사 여부·기준 가로/세로·다른 얼굴 및 재촬영 기준은 유지합니다. 기존 백분율 오차는 새 단위의 기본값 **0.5**로 교체하며 5%를 오차 5로 해석하지 않습니다. 읽기 시 기존 설정 파일은 수정하지 않고 다음 저장 시 최신 형식으로 기록합니다.

얼굴 높이 25%, 기울기 5도, 신뢰도 0.8, 기존 얼굴·파일·재촬영 검사는 유지합니다. 비율 검사 통과만으로 자동 정상에 분류하지 않습니다.

## 최신 샘플 전체 검사

정답 표시가 없는 {len(new):,}장을 새 실행 파일로 검사했습니다. 자동 분류 건수는 정확도나 오판정률을 뜻하지 않습니다.

| 항목 | 결과 |
|---|---:|
| 발견 / 처리 | {current['total']:,} / {current['processed']:,}장 |
| 정상 | {current['counts'].get('정상',0):,}장 |
| 확인 필요 | {current['counts'].get('확인 필요',0):,}장 |
| 파일 오류 | {current['counts'].get('파일 오류',0):,}장 |
| 비율 범위 밖 → 확인 필요 | {len(ratio_rows)}장 |
| 분석 예외 / 폴더 접근 오류 | {len(current['analysis_exceptions'])} / {len(current['discovery_issues'])}건 |
| 전체 검사 시간 | {seconds:.2f}초, 약 {rounded//60}분 {rounded%60}초 |
| 원본 보존 | 전체 SHA-256 일치 |
| 미리보기·이동·검색·빈 필터 | 모두 통과 |

이전 백분율 검사에서 새 기준으로 분류가 바뀐 사진은 {len(changed)}장입니다. 각각 이전 결과의 비율 사유를 새 계산으로 대체한 예상과 실제 실행 파일 결과가 일치했습니다. 다른 검사 사유는 유지됐고 사용자 지정 `128100020.jpg`도 재촬영 의심으로 유지됐습니다. 세부 비교는 `build/aspect-difference-comparison.json`입니다.

| 비율 범위 밖 사진 | 원래 표시 크기 | 환산 세로−가로 |
|---|---:|---:|
{examples}

## 검증과 배포

자동 테스트 **124개 모두 통과**했습니다. 0.5·1.5 경계 통과, 경계 밖, 픽셀 크기가 달라도 같은 모양의 환산 값 유지, 사용자 6:8 등의 다른 기준과 오차, EXIF·축소 전 크기, 허용 오차 비율 라벨·설명·값 저장, 이전 백분율 설정 복원을 검사했습니다. 기존 파일·얼굴·재촬영·CSV·취소·분석 엔진 복구도 통과했습니다.

실행 파일 하나만 한글·공백 경로의 읽기 전용 폴더에 복사하고 Python 개발 경로·환경변수를 제거하고 기본 TEMP/TMP를 없는 경로로 지정한 환경에서 전체 검사를 통과했습니다. 실제 설정 팝업 저장과 검사 당시 결과 보존도 확인했습니다. 관리자 권한 없이 설정·CSV 저장 권한, 읽기 금지·읽기 전용·파일 잠금 등 **{len(permissions['checks'])}개 권한 검사도 통과**했습니다. 내장 Python DLL을 사용했습니다.

별도 Python 미설치 물리 PC와 Windows 10 직접 검증은 남아 있습니다. 사용자 로컬 데이터 폴더에는 쓰기 권한이 필요합니다. 비율이 맞는 재촬영을 비율 검사만으로 검출할 수 없고, 기존 테두리 재촬영 검사의 누락·오검출 한계는 유지됩니다.

## 결과 파일

- 실행 파일: `dist/PhotoCheck.exe`, {exe.stat().st_size:,}바이트
- SHA-256: `{digest}`
- 전체 검사: `build/sample-frozen.json`, `build/sample-frozen.csv`
- 새 계산 사전 조사: `build/aspect-inventory.json`
- 이전과의 비교: `build/aspect-difference-comparison.json`
- 권한·기본 실행: `build/frozen-permissions.json`, `build/isolated-smoke.json`
- 변경한 팝업 화면: `build/theme-settings-basic.png`
- 이전 0.6 보고서: `build/TEST_RESULTS-criteria-0.6.md`, `build/sample-frozen-criteria-0.6.json`과 CSV
'''
(root/'TEST_RESULTS.md').write_text(document,encoding='utf-8')
print(json.dumps({k:comparison[k] for k in ('ok','total','counts','aspect_count','changed_files','elapsed_seconds')},ensure_ascii=True,indent=2))
