"""Check removals and direct/delay PE dependencies in the actual EXE archive."""
import hashlib
import json
from pathlib import Path
from build_artifact import executable_path
import pefile
from PyInstaller.archive.readers import CArchiveReader

root = Path(__file__).resolve().parent.parent
exe = executable_path(root)
archive = CArchiveReader(str(exe))
names = list(archive.toc)
removed = {'opencv_videoio_ffmpeg4110_64.dll','qpdf.dll','qt6pdf.dll',
           'qtvirtualkeyboardplugin.dll','qt6virtualkeyboard.dll','qt6qml.dll',
           'qt6quick.dll','qt6qmlmeta.dll','qt6qmlmodels.dll','qt6qmlworkerscript.dll',
           'onnxruntime.dll','_avif.cp312-win_amd64.pyd'}
assert not any(Path(name).name.casefold() in removed for name in names)
assert not any(name.replace('\\','/').startswith('mediapipe/modules/') and
               Path(name).suffix.casefold() in ('.tflite','.binarypb','.pbtxt') for name in names)
assert any(name.endswith('opencv_world3410.dll') for name in names)
assert any(name.endswith('opengl32sw.dll') for name in names)
assert all(any(name.replace('\\','/') == 'models/'+model for name in names) for model in
           ('face_landmarker.task','blaze_face_short_range.tflite','ppocrv3_det.onnx',
            'korean_ppocrv5_rec.onnx','korean_rec_dict.json'))
bad = []
native_count = 0
for name in names:
    if Path(name).suffix.casefold() not in ('.dll','.pyd'):
        continue
    native_count += 1
    pe = pefile.PE(data=archive.extract(name),fast_load=True)
    pe.parse_data_directories(directories=[1,13])
    for entries in (getattr(pe,'DIRECTORY_ENTRY_IMPORT',[]), getattr(pe,'DIRECTORY_ENTRY_DELAY_IMPORT',[])):
        for entry in entries:
            dependency = entry.dll.decode('ascii').casefold()
            if dependency in removed:
                bad.append((name,dependency))
assert not bad,bad
# Recorded size of the pre-compaction release; no old EXE backup is required.
size, previous = exe.stat().st_size, 182143567
assert size < previous
result = {'ok':True,'native_dependencies_checked':native_count,'bytes':size,
          'previous_bytes':previous,'reduced_bytes':previous-size,
          'reduction_percent':round((previous-size)/previous*100,2),
          'sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),
          'removed_files':sorted(removed), 'required_cpu_and_graphics_components_preserved':True}
(root/'build/compact-archive.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
