#!/usr/bin/env python3
import json, sys
from pathlib import Path
from visual_diff import compare_images

root=Path(sys.argv[1] if len(sys.argv)>1 else 'ab-output')
MEAN_TARGET=0.90
FLOOR_TARGET=0.85
rows=[]
for a in sorted(root.glob('*-A.png')):
    stem=a.name[:-6]
    b=root/(stem+'-B.png')
    if not b.exists():
        raise SystemExit(f'missing candidate screenshot: {b}')
    diff=root/(stem+'-diff.png')
    r=compare_images(a,b,grid_size=64,max_score=1.0,diff_path=diff,region_weighted=True)
    r['checkpoint']=stem
    (root/(stem+'-diff.json')).write_text(json.dumps(r,indent=2)+'\n')
    rows.append(r)
if not rows:
    raise SystemExit('no A/B screenshot pairs found')

mean_similarity=round(sum(r['similarity'] for r in rows)/len(rows),6)
worst=sorted(rows,key=lambda r:r['similarity'])
floor_similarity=round(worst[0]['similarity'],6)
summary={
 'schema':'awwwards-ab-checkpoints-v2',
 'score_mode':'region-weighted',
 'count':len(rows),
 'mean_score':round(sum(r['score'] for r in rows)/len(rows),6),
 'mean_similarity':mean_similarity,
 'floor_similarity':floor_similarity,
 'acceptance':{
   'mean_target':MEAN_TARGET,
   'floor_target':FLOOR_TARGET,
   'pass': bool(mean_similarity>=MEAN_TARGET and floor_similarity>=FLOOR_TARGET),
 },
 'worst':[{
   'checkpoint':r['checkpoint'],'score':r['score'],'similarity':r['similarity'],
   'global_score':r.get('global_score'),'weighted_score':r.get('weighted_score'),
 } for r in worst],
 'results':[{
   'checkpoint':r['checkpoint'],'score':r['score'],'similarity':r['similarity'],
   'global_score':r.get('global_score'),'weighted_score':r.get('weighted_score'),
   'metrics':r['metrics'],'diagnostics':r.get('diagnostics',{}),'regions':r.get('regions',[]),
 } for r in rows]
}
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')

weak=[]
for r in worst:
    if r['similarity'] >= FLOOR_TARGET and mean_similarity >= MEAN_TARGET:
        continue
    weak.append({
        'checkpoint':r['checkpoint'],
        'similarity':r['similarity'],
        'score':r['score'],
        'diagnostics':(r.get('diagnostics') or {}).get('summary',[])[:5],
        'regions':sorted([
            {
                'name':x.get('name'),
                'score':x.get('score'),
                'weight':x.get('weight'),
                'contribution':x.get('contribution'),
                'classification':x.get('classification'),
            } for x in r.get('regions',[])
        ], key=lambda x: float(x.get('contribution') or 0), reverse=True)[:4],
    })
repair={
 'schema':'awwwards-repair-context-v1',
 'target_a':'https://stateofaidesign.com/',
 'candidate_b':'https://louisalviss.github.io/awwwards-ai-design-clone-canary/',
 'policy':{
   'do_not_fetch_target_source':True,
   'do_not_copy_target_assets':True,
   'editable_files':['index.html','styles.css','script.js'],
   'max_rounds':3,
   'acceptance':summary['acceptance'],
 },
 'baseline':{'mean_similarity':mean_similarity,'floor_similarity':floor_similarity},
 'weak_checkpoints':weak,
 'instructions':[
   'Prioritize geometry/layout errors before color/media composition.',
   'Use diagnostics and screenshots as evidence; do not optimize blank/background regions.',
   'Keep responsive behavior correct at 1440x1000 and 412x915.',
   'Do not modify scoring, capture, workflows, evidence, or acceptance thresholds.',
 ],
}
(root/'repair-context.json').write_text(json.dumps(repair,indent=2)+'\n')
(root/'gate.json').write_text(json.dumps(summary['acceptance'],indent=2)+'\n')
print(json.dumps(summary,indent=2))
