"""Read-only cross-folder text detection spot check for visual assessment."""
import json
from pathlib import Path
import sys
sys.stdout.reconfigure(encoding='utf-8')
root = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root))
import numpy as np
from photocheck.criteria import Criteria
from photocheck.files import collect, load_image
from photocheck.text_detection import MODEL_NAME, TextDetector

paths = collect(root/'sample', True).paths
chosen = list(dict.fromkeys(paths[:24]+paths[::max(1,len(paths)//80)]))
detector = TextDetector((root/'models'/MODEL_NAME).read_bytes())
if len(sys.argv)>1:
    import cv2
    from types import SimpleNamespace
    net=cv2.dnn.readNetFromONNX(sys.argv[1])
    detector.net=SimpleNamespace(setInput=net.setInput, forward=net.forward)
found = []
for path in chosen:
    image, _, _ = load_image(path)
    if image is None:
        continue
    try:
        regions, metrics = detector.detect(np.asarray(image), Criteria())
        if regions:
            found.append({'file':str(path.relative_to(root/'sample')), 'regions':regions, 'metrics':metrics})
    finally:
        image.close()
data = {'checked':len(chosen),'suspected':len(found),'files':found}
(root/('build/text-spotcheck-alternative.json' if len(sys.argv)>1 else 'build/text-spotcheck.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(data,ensure_ascii=False))
