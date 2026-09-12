#!/usr/bin/env python3
import json, tempfile
from pathlib import Path
from visual_diff import ImageRGB, write_png
import subprocess
with tempfile.TemporaryDirectory() as td:
    root=Path(td)
    def img(path,hot=False):
        w=h=96; data=bytearray(bytes((245,245,245))*(w*h))
        if hot:
            for y in range(32):
                for x in range(32):
                    i=(y*w+x)*3; v=20 if (x//4+y//4)%2==0 else 235; data[i:i+3]=bytes((v,v,v))
        write_png(path,ImageRGB(w,h,bytes(data)))
    img(root/'desktop-hero-A.png',True); img(root/'desktop-hero-B.png',False)
    subprocess.run(['python3',str(Path(__file__).with_name('score-ab.py')),str(root)],check=True,capture_output=True,text=True)
    s=json.loads((root/'summary.json').read_text()); c=json.loads((root/'repair-context.json').read_text())
    assert s['schema']=='awwwards-ab-checkpoints-v2'
    assert s['score_mode']=='region-weighted'
    assert c['schema']=='awwwards-repair-context-v1'
    assert c['weak_checkpoints']
    assert c['policy']['editable_files']==['index.html','styles.css','script.js']
print('repair context test passed')
