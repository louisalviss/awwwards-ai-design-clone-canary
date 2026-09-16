#!/usr/bin/env python3
import base64, json, shutil, subprocess, tempfile
from pathlib import Path

# 1x1 PNG contract fixture.
PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2nAAAAABJRU5ErkJggg==')
repo=Path(__file__).resolve().parents[1]

# Run the importer against an isolated temporary repo fixture. Contract tests
# must never mutate the candidate working tree because candidate media/CSS is
# itself the subject of the subsequent A/B visual evaluation.
with tempfile.TemporaryDirectory() as td_raw:
    td=Path(td_raw)
    fixture=td/'repo'
    (fixture/'tools').mkdir(parents=True)
    (fixture/'assets/generated').mkdir(parents=True)
    shutil.copyfile(repo/'tools/media-reconstruction-plan.json', fixture/'tools/media-reconstruction-plan.json')
    (fixture/'assets/generated/media-generated.css').write_text('/* isolated contract fixture */\n')
    asset=td/'x.png'
    asset.write_bytes(PNG)

    cp=subprocess.run([
        'python3', str(repo/'tools/import-chat-media.py'),
        '--repo', str(fixture), '--region', 'intro-studio', '--asset', str(asset)
    ], capture_output=True, text=True)
    if cp.returncode:
        raise SystemExit(cp.stderr)

    d=json.loads(cp.stdout)
    assert d['source']=='chatgpt-image-in-chat'
    assert d['guard']['network_used'] is False and d['guard']['api_key_used'] is False
    assert d['asset'].startswith('assets/generated/')
    assert (fixture/d['asset']).exists()
    assert (fixture/'.media-reconstruction/chat-import.json').exists()
    css=(fixture/'assets/generated/media-generated.css').read_text()
    assert 'chat-media:intro-studio:begin' in css
    assert '.intro-visual' in css

print('in-chat media importer contract PASS')
