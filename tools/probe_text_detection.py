"""Read-only model/scale probe; no OCR transcription or image writes."""
from pathlib import Path
import time
import cv2
import numpy as np
from PIL import Image, ImageOps

root = Path(__file__).resolve().parent.parent
path = next((root / 'sample').rglob('71W298095.jpg'))
with Image.open(path) as original:
    rgb = np.asarray(ImageOps.exif_transpose(original).convert('RGB'))
h, w = rgb.shape[:2]
net = cv2.dnn.readNetFromONNX(str(root / 'build/text-det-probe.onnx'))
mean = np.array([.485, .456, .406], dtype=np.float32)
std = np.array([.229, .224, .225], dtype=np.float32)
for threads in (1, 2, 4):
    cv2.setNumThreads(threads)
    for edge in (384, 512, 640, 768, 960):
        size = (max(32, round(w*edge/max(h,w)/32)*32), max(32, round(h*edge/max(h,w)/32)*32))
        x = (cv2.resize(rgb[:, :, ::-1], size).astype(np.float32)/255-mean)/std
        durations = []
        for _ in range(3):
            net.setInput(x.transpose(2,0,1)[None])
            start = time.perf_counter()
            y = net.forward()[0,0]
            durations.append(time.perf_counter()-start)
        cs = cv2.findContours((y>.3).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]
        boxes = []
        for c in cs:
            if cv2.contourArea(c) <= 8:
                continue
            mask = cv2.drawContours(np.zeros(y.shape, dtype=np.uint8), [c], -1, 1, -1)
            boxes.append((cv2.boundingRect(c), round(cv2.mean(y, mask)[0],4)))
        print(threads, edge, round(min(durations)*1000,2), boxes, flush=True)
print('jpeg_count', len(list((root/'sample').rglob('*.jpg'))))
