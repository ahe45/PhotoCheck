"""Read-only metadata inventory for the configured photo aspect ratio."""
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path
import sys

root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root))
from PIL import Image
from photocheck.criteria import Criteria
from photocheck.files import collect

criteria=Criteria()
collection=collect(root/'sample',True)
dimensions=Counter()
outside=[]
errors=[]
for path in collection.paths:
    try:
        with Image.open(path) as image:
            width,height=image.size
            if image.getexif().get(274,1) in (5,6,7,8):
                width,height=height,width
        dimensions[(width,height)]+=1
        actual=Decimal(height)*Decimal(str(criteria.aspect_width))
        expected=Decimal(width)*Decimal(str(criteria.aspect_height))
        tolerance=Decimal(width)*Decimal(str(criteria.aspect_tolerance))
        if abs(actual-expected)>tolerance:
            outside.append({'file':str(path.relative_to(root/'sample')),'width':width,'height':height,
                            'ratio':round(width/height,6),'difference':round(criteria.aspect_width*(height/width-1),6)})
    except Exception as error:
        errors.append({'file':str(path.relative_to(root/'sample')),'error':str(error)})
report={'total':len(collection.paths),'outside_count':len(outside),'outside':outside,'errors':errors,
        'excluded':collection.excluded,'criteria':criteria.snapshot(),
        'dimensions':[{'width':w,'height':h,'count':n} for (w,h),n in dimensions.most_common()]}
(root/'build/aspect-inventory.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:report[k] for k in ('total','outside_count','excluded')},ensure_ascii=True))
print('Dimension types:',len(dimensions))
print(outside[:12])
