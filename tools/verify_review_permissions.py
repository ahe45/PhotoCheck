"""Isolated packaged permission checks using a generated JPEG, never sample photos."""
import json
import os
from pathlib import Path
from build_artifact import executable_path
import shutil
import subprocess
import tempfile
from PIL import Image

root=Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix='photocheck-엑셀 복사 권한-') as folder:
    fixture=Path(folder)
    executable=fixture/executable_path(root).name
    shutil.copyfile(executable_path(root),executable)
    photo=fixture/'임시 생성 이미지.jpg'
    Image.new('RGB',(300,400),'white').save(photo)
    report=fixture/'권한.json'
    env={key:value for key,value in os.environ.items() if not key.startswith(('PYTHON','QT_'))}
    env['PATH']=str(Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32')
    env['LOCALAPPDATA']=str(fixture/'사용자 데이터')
    env['TMP']=env['TEMP']=str(fixture)
    result=subprocess.run([str(executable),'--permission-test',str(photo),str(report)],
                          cwd=fixture,env=env,timeout=90,creationflags=subprocess.CREATE_NO_WINDOW)
    data=json.loads(report.read_text(encoding='utf-8'))
    (root/'build/review-frozen-permissions.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    assert result.returncode == 0 and data['ok'] and data['frozen'] and not data['is_admin'],data
    assert str(fixture).casefold() in data['python_dll'].casefold() and '_mei' in data['python_dll'].casefold(),data
    print(json.dumps({'ok':data['ok'],'checks':data['checks'],'sample_photos_used':False}))
