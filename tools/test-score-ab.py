#!/usr/bin/env python3
import json, subprocess, sys, tempfile
from pathlib import Path
from visual_diff import solid_image, write_png

with tempfile.TemporaryDirectory() as td:
    root=Path(td)
    # Candidate closer to A than baseline for both checkpoints.
    fixtures={
      'desktop-one':((0,0,0),(20,20,20),(80,80,80)),
      'mobile-two':((120,120,120),(130,130,130),(180,180,180)),
    }
    for stem,(a,b,base) in fixtures.items():
        write_png(root/f'{stem}-A.png',solid_image(32,32,a))
        write_png(root/f'{stem}-B.png',solid_image(32,32,b))
        write_png(root/f'{stem}-BASE.png',solid_image(32,32,base))
    subprocess.run([sys.executable,str(Path(__file__).with_name('score-ab.py')),str(root)],check=True,stdout=subprocess.DEVNULL)
    s=json.loads((root/'summary.json').read_text())
    assert s['schema']=='awwwards-ab-checkpoints-v3'
    assert s['differential']['available'] is True
    assert s['differential']['reference_reused'] is True
    assert s['differential']['candidate_minus_baseline_mean'] > 0
    assert all(r['delta_vs_baseline'] > 0 for r in s['results'])
print('differential scorer contract PASS')
