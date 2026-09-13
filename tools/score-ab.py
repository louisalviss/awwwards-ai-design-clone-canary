#!/usr/bin/env python3
import json, sys
from pathlib import Path
from visual_diff import compare_images

root=Path(sys.argv[1] if len(sys.argv)>1 else 'ab-output')
MEAN_TARGET=0.90
FLOOR_TARGET=0.85

def compact(r):
    return {
      'checkpoint':r['checkpoint'],'score':r['score'],'similarity':r['similarity'],
      'global_score':r.get('global_score'),'weighted_score':r.get('weighted_score'),
    }

def detail(r):
    return {
      **compact(r), 'metrics':r['metrics'],'diagnostics':r.get('diagnostics',{}),'regions':r.get('regions',[]),
    }

def aggregate(rows):
    mean=round(sum(r['similarity'] for r in rows)/len(rows),6)
    worst=sorted(rows,key=lambda r:r['similarity'])
    return mean, round(worst[0]['similarity'],6), worst

candidate=[]
baseline=[]
for a in sorted(root.glob('*-A.png')):
    stem=a.name[:-6]
    b=root/(stem+'-B.png')
    if not b.exists(): raise SystemExit(f'missing candidate screenshot: {b}')
    r=compare_images(a,b,grid_size=64,max_score=1.0,diff_path=root/(stem+'-diff.png'),region_weighted=True)
    r['checkpoint']=stem
    (root/(stem+'-diff.json')).write_text(json.dumps(r,indent=2)+'\n')
    candidate.append(r)
    base=root/(stem+'-BASE.png')
    if base.exists():
        br=compare_images(a,base,grid_size=64,max_score=1.0,diff_path=root/(stem+'-base-diff.png'),region_weighted=True)
        br['checkpoint']=stem
        (root/(stem+'-base-diff.json')).write_text(json.dumps(br,indent=2)+'\n')
        baseline.append(br)
if not candidate: raise SystemExit('no A/B screenshot pairs found')
if baseline and len(baseline)!=len(candidate): raise SystemExit('incomplete baseline screenshot set')

mean_similarity,floor_similarity,worst=aggregate(candidate)
baseline_map={r['checkpoint']:r for r in baseline}
if baseline:
    baseline_mean,baseline_floor,baseline_worst=aggregate(baseline)
    differential={
      'available':True,
      'reference_reused':True,
      'baseline':'main',
      'baseline_mean_similarity':baseline_mean,
      'baseline_floor_similarity':baseline_floor,
      'candidate_minus_baseline_mean':round(mean_similarity-baseline_mean,6),
      'candidate_minus_baseline_floor':round(floor_similarity-baseline_floor,6),
      'non_regression':bool(mean_similarity>=baseline_mean and floor_similarity>=min(FLOOR_TARGET,baseline_floor)),
    }
else:
    differential={'available':False,'reference_reused':False}

results=[]
for r in candidate:
    row=detail(r)
    br=baseline_map.get(r['checkpoint'])
    if br:
        row['baseline_similarity']=br['similarity']
        row['delta_vs_baseline']=round(r['similarity']-br['similarity'],6)
    results.append(row)

summary={
 'schema':'awwwards-ab-checkpoints-v3',
 'score_mode':'region-weighted',
 'count':len(candidate),
 'mean_score':round(sum(r['score'] for r in candidate)/len(candidate),6),
 'mean_similarity':mean_similarity,
 'floor_similarity':floor_similarity,
 'acceptance':{
   'mean_target':MEAN_TARGET,'floor_target':FLOOR_TARGET,
   'pass':bool(mean_similarity>=MEAN_TARGET and floor_similarity>=FLOOR_TARGET),
 },
 'differential':differential,
 'worst':[compact(r) for r in worst],
 'results':results,
}
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')

weak=[]
for r in worst:
    weak.append({
      'checkpoint':r['checkpoint'],'similarity':r['similarity'],'score':r['score'],
      'baseline_similarity':baseline_map.get(r['checkpoint'],{}).get('similarity'),
      'delta_vs_baseline':round(r['similarity']-baseline_map[r['checkpoint']]['similarity'],6) if r['checkpoint'] in baseline_map else None,
      'diagnostics':(r.get('diagnostics') or {}).get('summary',[])[:5],
      'regions':sorted([{
        'name':x.get('name'),'score':x.get('score'),'weight':x.get('weight'),
        'contribution':x.get('contribution'),'classification':x.get('classification'),
      } for x in r.get('regions',[])],key=lambda x:float(x.get('contribution') or 0),reverse=True)[:4],
    })
repair={
 'schema':'awwwards-repair-context-v2',
 'target_a':'https://stateofaidesign.com/',
 'candidate_b':'https://louisalviss.github.io/awwwards-ai-design-clone-canary/',
 'policy':{
   'do_not_fetch_target_source':True,'do_not_copy_target_assets':True,
   'editable_files':['index.html','styles.css','script.js'],'max_rounds':3,
   'acceptance':summary['acceptance'],
 },
 'baseline':{'mean_similarity':mean_similarity,'floor_similarity':floor_similarity},
 'comparison_to_main':differential,
 'weak_checkpoints':weak,
 'instructions':[
   'Prioritize geometry/layout errors before color/media composition.',
   'Use diagnostics and screenshots as evidence; do not optimize blank/background regions.',
   'On pull requests, use candidate-vs-main deltas from the same A reference frame to judge improvement.',
   'Keep responsive behavior correct at 1440x1000 and 412x915.',
   'Do not modify scoring, capture, workflows, evidence, or acceptance thresholds during repair rounds.',
 ],
}
(root/'repair-context.json').write_text(json.dumps(repair,indent=2)+'\n')
(root/'gate.json').write_text(json.dumps({'acceptance':summary['acceptance'],'differential':differential},indent=2)+'\n')
print(json.dumps(summary,indent=2))
