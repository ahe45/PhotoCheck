"""Compare filled-region and rotated-box confidence on real review examples."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import cv2
import numpy as np
from PIL import Image
from photocheck.criteria import Criteria
from photocheck.text_detection import MODEL_NAME, TextDetector

root=Path(__file__).resolve().parent.parent
detector=TextDetector((root/'models'/MODEL_NAME).read_bytes())
for name in ('71W298095.jpg','120201228.jpg','71W298020.jpg','125100395.jpg','120701218.jpg','120701097.jpg'):
    with Image.open(next((root/'sample').rglob(name))) as source:
        rgb=np.array(source.convert('RGB'))
    regions,_=detector.detect(rgb,Criteria())
    probability=detector.net.forward()
    cs=cv2.findContours((probability>.3).astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]
    scores=[]
    for c in cs:
        if cv2.contourArea(c)<6 or min(cv2.minAreaRect(c)[1])<3:
            continue
        mask=cv2.drawContours(np.zeros(probability.shape,np.uint8),[c],-1,1,-1)
        raw=cv2.mean(probability,mask)[0]
        polygon=cv2.boxPoints(cv2.minAreaRect(c)).astype(np.int32)
        mask=cv2.fillPoly(np.zeros(probability.shape,np.uint8),[polygon],1)
        rect=cv2.mean(probability,mask)[0]
        scores.append((round(raw,4),round(rect,4)))
    print(name,scores,flush=True)
