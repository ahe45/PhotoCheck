from pathlib import Path
import runpy
from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH)
version = runpy.run_path(str(root / 'photocheck' / '__init__.py'))['__version__']
mp_data, mp_binaries, mp_hidden = collect_all('mediapipe', filter_submodules=lambda name:
    not any(part in name for part in ('.test', '.benchmark', '.genai', '.metadata', '.solutions')))
# Task APIs load our two verified model buffers, never legacy Solutions assets.
mp_data = [(source, destination) for source, destination in mp_data
           if Path(source).suffix.casefold() not in ('.tflite', '.binarypb', '.pbtxt')]
analysis = Analysis(
    [str(root / 'main.py')],
    pathex=[str(root)],
    binaries=mp_binaries,
    datas=mp_data + [(str(root / 'models' / name), 'models') for name in
                    ('manifest.json', 'blaze_face_short_range.tflite', 'face_landmarker.task',
                     'ppocrv3_det.onnx', 'korean_ppocrv5_rec.onnx', 'korean_rec_dict.json')]
                  + [(str(root / 'licenses'), 'licenses')],
    hiddenimports=mp_hidden,
    runtime_hooks=[str(root / 'tools' / 'runtime_paths.py')],
    excludes=['pytest', 'tkinter', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
              'PySide6.QtQml', 'PySide6.QtQuick', 'IPython', 'jax', 'jaxlib',
              'tensorflow', 'torch', 'yaml', 'openpyxl', 'PIL.AvifImagePlugin', 'PIL._avif'],
    hooksconfig={'matplotlib': {'backends': ['Agg']}},
    noarchive=False,
)
# Qt uses the native ICU API shipped with Windows 10/11. A development PATH
# containing Poppler/Conda can cause PyInstaller to pick an incompatible ICU DLL
# with version-suffixed exports. Let Windows supply its native ICU instead.
analysis.binaries = [entry for entry in analysis.binaries
                     if not Path(entry[0]).name.casefold().startswith('icu')]
# Still-image Widgets UI: no video codec, PDF viewer or virtual keyboard/QML.
# Preserve MediaPipe's directly linked opencv_world DLL and Qt's software GL
# fallback, native input, raster plugins and Windows platform compatibility.
unused = {'qt6pdf.dll', 'qt6quick.dll', 'qt6qml.dll', 'qt6qmlmodels.dll',
          'qt6qmlmetatypes.dll', 'qt6qmlmeta.dll', 'qt6qmlworkerscript.dll', 'qt6virtualkeyboard.dll',
          'qpdf.dll', 'qtvirtualkeyboardplugin.dll', 'opencv_videoio_ffmpeg4110_64.dll'}
# The Python CPU binding contains its inference core. The separate C-API DLL
# has no import from that binding or any application code; keep shared provider
# support. Archive dependency inspection and isolated OCR validate this cut.
unused.add('onnxruntime.dll')
analysis.binaries = [entry for entry in analysis.binaries
                     if Path(entry[0]).name.casefold() not in unused]
analysis.datas = [entry for entry in analysis.datas
                 if not (entry[0].replace('\\', '/').startswith('mediapipe/modules/')
                         and Path(entry[0]).suffix.casefold() in ('.tflite', '.binarypb', '.pbtxt'))]
archive = PYZ(analysis.pure)
exe = EXE(archive, analysis.scripts, analysis.binaries, analysis.datas,
          name=f'PhotoCheck_{version}', console=False, debug=False, strip=False, upx=False,
          runtime_tmpdir=r'%LOCALAPPDATA%\PhotoCheck\Runtime',
          uac_admin=False, uac_uiaccess=False)
