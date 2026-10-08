$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv312\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw '개발 환경이 없습니다. 먼저 py -3.12 -m venv .venv312 및 의존성 설치를 진행하세요.'
}
& $taskPython tools\download_models.py
if ($LASTEXITCODE -ne 0) { throw '모델 확인 실패' }
& $taskPython -m pytest -q -k 'not (real_sample_paper or prefilter_skips_line or real_spawned_engine_receives_custom or real_signature_and or face_eyes_and_glasses)'
if ($LASTEXITCODE -ne 0) { throw '검증 실패' }
& $taskPython tools\collect_licenses.py
if ($LASTEXITCODE -ne 0) { throw '라이선스 수집 실패' }
& $taskPython -m PyInstaller --noconfirm PhotoCheck.spec
if ($LASTEXITCODE -ne 0) { throw '실행 파일 빌드 실패' }
& $taskPython tools\verify_exe.py
if ($LASTEXITCODE -ne 0) { throw '배포 실행 검증 실패' }
& $taskPython tools\verify_review_permissions.py
if ($LASTEXITCODE -ne 0) { throw '권한 검증 실패' }
Write-Host '생성 완료: dist\PhotoCheck.exe'
