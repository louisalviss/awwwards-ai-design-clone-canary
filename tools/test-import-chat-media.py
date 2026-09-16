#!/usr/bin/env python3
import base64, json, subprocess, tempfile
from pathlib import Path
# 1x1 PNG
PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2nAAAAABJRU5ErkJggg==')
repo=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as td:
    td=Path(td); asset=td/'x.png'; asset.write_bytes(PNG)
    cp=subprocess.run(['python3',str(repo/'tools/import-chat-media.py'),'--repo',str(repo),'--region','intro-studio','--asset',str(asset)],capture_output=True,text=True)
    if cp.returncode: raise SystemExit(cp.stderr)
    d=json.loads(cp.stdout)
    assert d['source']=='chatgpt-image-in-chat'
    assert d['guard']['network_used'] is False and d['guard']['api_key_used'] is False
    assert d['asset'].startswith('assets/generated/')
    out=repo/d['asset']; assert out.exists()
    # cleanup only files created by this contract test
    out.unlink()
    rec=repo/'.media-reconstruction/chat-import.json'
    if rec.exists(): rec.unlink()
    css=repo/'assets/generated/media-generated.css'
    txt=css.read_text(); b='/* chat-media:intro-studio:begin */'; e='/* chat-media:intro-studio:end */'
    if b in txt and e in txt:
        css.write_text((txt.split(b,1)[0]+txt.split(e,1)[1].lstrip('\n')).rstrip()+'\n')
print('in-chat media importer contract PASS')
