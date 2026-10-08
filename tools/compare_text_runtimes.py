"""Check reference ONNX CPU runtime against OpenCV using identical tensors."""
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import cv2
import numpy as np
from PIL import Image
from photocheck.text_detection import regions_from_map

root = Path(__file__).resolve().parent.parent
names = ('71W298095.jpg','125100013.jpg','360212006.jpg','360212011.jpg')
cv2.setNumThreads(4)
for name in names:
    path = next((root/'sample').rglob(name))
    with Image.open(path) as original:
        rgb = np.array(original.convert('RGB'))
    h,w = rgb.shape[:2]
    for edge in (0,512,960):
        scale = min(1.,512/max(h,w)) if not edge else edge/max(h,w)
        size = tuple(max(32,round(v*scale/32)*32) for v in (w,h))
        x = (cv2.resize(rgb[:,:,::-1],size).astype(np.float32)/255-np.array([.485,.456,.406],np.float32))/np.array([.229,.224,.225],np.float32)
        tensor = np.ascontiguousarray(x.transpose(2,0,1)[None])
        net = cv2.dnn.readNetFromONNX(str(root/'models/ppocrv5_mobile_det.onnx'))
        net.setInput(tensor)
        t = time.perf_counter()
        y = net.forward()[0,0]
        print(name,edge,'cv',round((time.perf_counter()-t)*1000,2),regions_from_map(y,.6,.008),flush=True)
        v3 = cv2.dnn.readNetFromONNX(str(root/'build/text-det-v3-probe.onnx'))
        v3.setInput(tensor)
        t = time.perf_counter()
        v3_map = v3.forward()
        print(name,edge,'cv-v3',round((time.perf_counter()-t)*1000,2),regions_from_map(v3_map,.6,.008),flush=True)
        try:
            import onnxruntime as ort
        except ImportError:
            continue
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 4
        session = ort.InferenceSession(str(root/'models/ppocrv5_mobile_det.onnx'),opts,providers=['CPUExecutionProvider'])
        t = time.perf_counter()
        other = session.run(None,{session.get_inputs()[0].name:tensor})[0][0,0]
        print(name,edge,'ort',round((time.perf_counter()-t)*1000,2),regions_from_map(other,.6,.008),'maxdiff',float(np.abs(other-y).max()),flush=True)
