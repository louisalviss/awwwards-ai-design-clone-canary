#!/usr/bin/env python3
import importlib.util, json, subprocess, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
# Use the repository's dependency-free PNG implementation.
sys.path.insert(0,str(ROOT/'tools'))
from visual_diff import solid_image, write_png

with tempfile.TemporaryDirectory() as td:
    t=Path(td); captures=t/'captures'; captures.mkdir(); repo=t/'repo'; (repo/'assets/generated').mkdir(parents=True); (repo/'tools').mkdir()
    write_png(captures/'desktop-test-A.png', solid_image(100,100,(120,130,140)))
    plan={
      'schema':'media-reconstruction-plan-v1','model':'gpt-image-2.5-sunburst','quality':'medium','max_regions':1,'max_source_coverage':0.75,
      'regions':[{'id':'box','source':'desktop-test-A.png','crop':{'x':10,'y':10,'width':50,'height':50},'size':'1024x1024',
                  'output':'assets/generated/box.png','prompt':'Create a new original editorial photograph with generic fictional people and neutral visual details only. No logos or text.',
                  'apply':{'selector':'.box','deactivate':['.box::before']}}]
    }
    pp=repo/'tools/plan.json'; pp.write_text(json.dumps(plan))
    cmd=[sys.executable,str(ROOT/'tools/media-reconstruct.py'),'--repo',str(repo),'--plan',str(pp),'--capture-root',str(captures)]
    out=subprocess.check_output(cmd,text=True)
    run=json.loads((repo/'.media-reconstruction/run.json').read_text())
    assert run['mode']=='dry-run' and run['region_count']==1
    assert abs(run['regions'][0]['crop_coverage']-.25)<1e-6
    assert not (repo/'assets/generated/box.png').exists()
    # Generated CSS must use a URL relative to assets/generated for GitHub Pages subpaths.
    spec=importlib.util.spec_from_file_location('media_reconstruct', ROOT/'tools/media-reconstruct.py')
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    css=mod.css_for(plan['regions'][0])
    assert 'url("box.png")' in css and '/assets/' not in css
    # Fail closed on a near-full screenshot crop.
    plan['regions'][0]['crop']={'x':0,'y':0,'width':100,'height':100}
    pp.write_text(json.dumps(plan))
    p=subprocess.run(cmd,text=True,capture_output=True)
    assert p.returncode!=0 and 'coverage' in (p.stderr+p.stdout)
print('media reconstructor contract PASS')
