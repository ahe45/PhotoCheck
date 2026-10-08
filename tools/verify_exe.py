"""Verify one EXE in an owned read-only folder, using generated fixtures only."""
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parent.parent
rows=csv.reader(subprocess.check_output(['whoami','/user','/fo','csv','/nh'],encoding='utf-8',errors='replace').splitlines())
sid=next(row[1] for row in rows if len(row)>1 and row[1].startswith('S-1-'))
with tempfile.TemporaryDirectory(prefix='사진 검수 배포-') as folder:
    destination=Path(folder).resolve()
    app_dir=destination/'읽기 전용 실행 폴더'
    app_dir.mkdir()
    executable=app_dir/'PhotoCheck.exe'
    shutil.copyfile(root/'dist/PhotoCheck.exe',executable)
    report=destination/'실행 검증.json'
    env={key:value for key,value in os.environ.items() if not key.startswith(('PYTHON','QT_'))}
    env['PATH']=str(Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32')
    env['QT_QPA_PLATFORM']='offscreen'
    env['LOCALAPPDATA']=str(destination/'사용자 데이터')
    env['TMP']=env['TEMP']=str(destination/'없는 임시 경로')
    assert app_dir.resolve().is_relative_to(destination)
    deny=subprocess.run(['icacls',str(app_dir),'/deny',f'*{sid}:(W)'],capture_output=True)
    assert deny.returncode == 0
    try:
        process=subprocess.run([str(executable),'--smoke-test',str(report)],cwd=app_dir,env=env,
                               timeout=45,creationflags=subprocess.CREATE_NO_WINDOW)
        if not report.exists():
            raise RuntimeError(f'실행 보고서 없음; 종료 코드 {process.returncode}')
        result=json.loads(report.read_text(encoding='utf-8'))
        result['deployment_conditions']={'single_executable_only':True,'python_paths_removed':True,
            'readonly_executable_directory':True,'invalid_default_tmp':True,'generated_images_only':True}
        output=root/'build/isolated-smoke.json'
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        for suffix in ('.png','.xlsx'):
            source=report.with_suffix(suffix)
            if source.exists():
                shutil.copyfile(source,output.with_suffix(suffix))
        for filename in ('copy-progress.png','copy-complete.png'):
            source=report.with_name(filename)
            if source.exists():
                shutil.copyfile(source,output.with_name(filename))
        assert process.returncode == 0 and result['ok'] and result['frozen'],result
        assert result.get('review_workflow') and all(result['review_workflow'].values()),result
        print(json.dumps(result,ensure_ascii=True))
    finally:
        restored=subprocess.run(['icacls',str(app_dir),'/remove:d',f'*{sid}'],capture_output=True)
        assert restored.returncode == 0
