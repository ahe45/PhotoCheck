"""Development probe: report counts only, never transcribed photo contents."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cv2
import numpy as np
import onnxruntime as ort
import yaml
from PIL import Image, ImageDraw, ImageFont
from photocheck.criteria import Criteria
from photocheck.text_detection import TextDetector

root = Path(__file__).resolve().parent.parent
data = yaml.safe_load((root/'build/ocr-probe/inference.yml').read_text(encoding='utf-8'))
chars = [''] + data['PostProcess']['character_dict'] + [' ']
options = ort.SessionOptions()
options.log_severity_level = 3
options.intra_op_num_threads = 4
session = ort.InferenceSession(str(root/'build/ocr-probe/inference.onnx'), options, providers=['CPUExecutionProvider'])
det = TextDetector((root/'models/ppocrv3_det.onnx').read_bytes())

def recognize(rgb, box, padding):
    H,W = rgb.shape[:2]
    x,y,w,h = box
    x,y,w,h = x*W,y*H,w*W,h*H
    px,py = h*padding,h*.25
    crop = rgb[max(0,int(y-py)):min(H,int(y+h+py)),max(0,int(x-px)):min(W,int(x+w+px)),::-1]
    hh,ww = crop.shape[:2]
    width = min(640,max(32,int(np.ceil(48*ww/hh))))
    tensor = (cv2.resize(crop,(width,48)).astype(np.float32)/127.5-1).transpose(2,0,1)[None]
    o = session.run(None, {'x':np.ascontiguousarray(tensor)})[0][0]
    ids = o.argmax(-1)
    scores = o.max(-1)
    tokens = [(chars[int(i)],float(s)) for j,(i,s) in enumerate(zip(ids,scores)) if i and (j==0 or i!=ids[j-1])]
    runs=[]; run=0
    for char,score in tokens:
        if char.isalnum() and score>=.6:
            run+=1
        else:
            runs.append(run); run=0
    runs.append(run)
    return {'chars':len(tokens),'max_run':max(runs),'min_score':round(min([s for _,s in tokens],default=0),3)}

print('dictionary',len(chars),'model classes',11947)
photo = next((root/'sample').rglob('71W298095.jpg'))
rgb = np.array(Image.open(photo).convert('RGB'))
for box,score in det.detect(rgb,Criteria())[0]:
    print('signature',box,score,[(p,recognize(rgb,box,p)) for p in (.3,.6,1,2)])
for text in ('A','AB','ABC','AAA','A B C','12','123','가나','가나다','검수 TEST'):
    image = Image.new('RGB',(300,400),'white')
    ImageDraw.Draw(image).text((20,350),text,font=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',24),fill='black')
    rgb=np.array(image)
    boxes=det.detect(rgb,Criteria())[0]
    print(ascii(text),[(p,recognize(rgb,box,p)) for box,_ in boxes for p in (.3,.6,1)])
