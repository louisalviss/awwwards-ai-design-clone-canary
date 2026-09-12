#!/usr/bin/env python3
import importlib.util, json, sys
from pathlib import Path
root=Path(sys.argv[1] if len(sys.argv)>1 else 'ab-output')
spec=importlib.util.spec_from_file_location('visual_diff', Path(__file__).with_name('visual_diff.py'))
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
rows=[]
for a in sorted(root.glob('*-A.png')):
    stem=a.name[:-6]
    b=root/(stem+'-B.png')
    diff=root/(stem+'-diff.png')
    r=mod.compare_images(a,b,grid_size=64,max_score=1.0,diff_path=diff)
    r['checkpoint']=stem
    (root/(stem+'-diff.json')).write_text(json.dumps(r,indent=2)+'\n')
    rows.append(r)
summary={
 'schema':'awwwards-ab-checkpoints-v1',
 'count':len(rows),
 'mean_score':round(sum(r['score'] for r in rows)/len(rows),6),
 'mean_similarity':round(sum(r['similarity'] for r in rows)/len(rows),6),
 'worst':sorted([{'checkpoint':r['checkpoint'],'score':r['score'],'similarity':r['similarity']} for r in rows],key=lambda x:x['score'],reverse=True),
 'results':[{'checkpoint':r['checkpoint'],'score':r['score'],'similarity':r['similarity'],'metrics':r['metrics']} for r in rows]
}
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
