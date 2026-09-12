#!/usr/bin/env python3
"""Fail-closed adapter for one visual repair round.

It deliberately does not score or push. CI is the independent judge. The driver
only supplies bounded evidence to an external repair agent and rejects edits to
anything outside the three candidate-site files.
"""
from __future__ import annotations
import argparse, json, os, shlex, subprocess, sys
from pathlib import Path

ALLOWED={'index.html','styles.css','script.js'}

def git(root,*args,check=True):
    return subprocess.run(['git',*args],cwd=root,text=True,capture_output=True,check=check)

def changed(root):
    out=git(root,'status','--porcelain=v1').stdout.splitlines()
    files=[]
    for line in out:
        p=line[3:].strip()
        if ' -> ' in p: p=p.split(' -> ',1)[1]
        files.append(p)
    return sorted(set(files))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--root',default='.')
    ap.add_argument('--context',default='ab-output/repair-context.json')
    ap.add_argument('--adapter',default=os.environ.get('VISUAL_REPAIR_ADAPTER',''))
    args=ap.parse_args()
    root=Path(args.root).resolve(); context=(root/args.context).resolve()
    if not (root/'.git').exists(): raise SystemExit('repair root must be a git repository')
    if not context.is_file(): raise SystemExit(f'missing repair context: {context}')
    dirty=changed(root)
    if dirty: raise SystemExit('repair root must be clean before repair: '+', '.join(dirty))
    ctx=json.loads(context.read_text())
    if ctx.get('schema')!='awwwards-repair-context-v1': raise SystemExit('unsupported repair context schema')
    adapter=args.adapter.strip()
    if not adapter: raise SystemExit('repair adapter not configured')
    prompt=(
      'Perform exactly one bounded visual repair round for site B.\n'
      'You may edit only index.html, styles.css, script.js. Never fetch or inspect target A source/HTML/CSS/JS/assets. '
      'Never edit tools, workflows, screenshots, scoring code, evidence, thresholds, or repair context. '
      'Use the JSON evidence below. Prefer layout/geometry fixes over cosmetic changes. '
      'Do not commit or push.\n\nREPAIR_CONTEXT_JSON\n'+json.dumps(ctx,indent=2)+'\n'
    )
    cmd=shlex.split(adapter)
    proc=subprocess.run(cmd,cwd=root,input=prompt,text=True)
    if proc.returncode!=0:
        git(root,'reset','--hard','HEAD',check=False)
        git(root,'clean','-fd',check=False)
        raise SystemExit(f'repair adapter failed: {proc.returncode}')
    bad=[p for p in changed(root) if p not in ALLOWED]
    if bad:
        git(root,'reset','--hard','HEAD',check=False); git(root,'clean','-fd',check=False)
        raise SystemExit('repair touched forbidden paths: '+', '.join(bad))
    edits=changed(root)
    if not edits: raise SystemExit('repair made no allowed changes')
    print(json.dumps({'ok':True,'schema':'awwwards-repair-round-v1','changed_files':edits},indent=2))

if __name__=='__main__': main()
