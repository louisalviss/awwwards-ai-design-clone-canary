#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, shutil
from pathlib import Path

ALLOWED_EXT={'.png','.jpg','.jpeg','.webp'}
MAX_BYTES=15*1024*1024

def sha256(p:Path)->str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()

def parse_jpeg_size(p:Path):
    b=p.read_bytes()
    if not b.startswith(b'\xff\xd8'): return None
    i=2
    while i+9 < len(b):
        if b[i] != 0xFF:
            i += 1; continue
        marker=b[i+1]; i += 2
        if marker in (0xD8,0xD9): continue
        if i+2>len(b): break
        seg=int.from_bytes(b[i:i+2],'big')
        if marker in tuple(range(0xC0,0xC4))+tuple(range(0xC5,0xC8))+tuple(range(0xC9,0xCC))+tuple(range(0xCD,0xD0)):
            if i+7<=len(b):
                return int.from_bytes(b[i+5:i+7],'big'), int.from_bytes(b[i+3:i+5],'big')
        i += max(seg,2)
    return None

def parse_png_size(p:Path):
    b=p.read_bytes()[:24]
    if len(b)>=24 and b[:8]==b'\x89PNG\r\n\x1a\n':
        return int.from_bytes(b[16:20],'big'), int.from_bytes(b[20:24],'big')
    return None

def image_size(p:Path):
    return parse_png_size(p) or parse_jpeg_size(p)

def main():
    ap=argparse.ArgumentParser(description='Import an asset created by GPT Image in ChatGPT into one bounded media region.')
    ap.add_argument('--repo',default='.')
    ap.add_argument('--plan',default='tools/media-reconstruction-plan.json')
    ap.add_argument('--region',required=True)
    ap.add_argument('--asset',required=True)
    ap.add_argument('--source-label',default='chatgpt-image-in-chat')
    args=ap.parse_args()
    repo=Path(args.repo).resolve(); plan_path=(repo/args.plan).resolve(); asset=Path(args.asset).resolve()
    plan=json.loads(plan_path.read_text())
    region=next((r for r in plan['regions'] if r['id']==args.region),None)
    if not region: raise SystemExit(f'unknown region: {args.region}')
    if not asset.is_file(): raise SystemExit('asset not found')
    if asset.suffix.lower() not in ALLOWED_EXT: raise SystemExit('unsupported asset extension')
    if asset.stat().st_size>MAX_BYTES: raise SystemExit('asset exceeds 15MB')
    dims=image_size(asset)
    if not dims: raise SystemExit('asset is not a supported parseable PNG/JPEG')
    out_rel=Path('assets/generated')/(args.region+'-chat'+asset.suffix.lower())
    out=(repo/out_rel).resolve()
    allowed=(repo/'assets/generated').resolve()
    if allowed not in out.parents: raise SystemExit('output escaped assets/generated')
    out.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(asset,out)
    css_path=repo/'assets/generated/media-generated.css'
    css=(css_path.read_text() if css_path.exists() else '')
    selector=region['apply']['selector']
    # Replace only this importer-owned block for idempotency.
    begin=f'/* chat-media:{args.region}:begin */'; end=f'/* chat-media:{args.region}:end */'
    if begin in css and end in css:
        pre=css.split(begin,1)[0]; post=css.split(end,1)[1]; css=pre+post.lstrip('\n')
    url='./'+out_rel.name
    block=(f'\n{begin}\n{selector}{{background-image:url("{url}")!important;background-size:cover!important;'
           f'background-position:center!important;background-repeat:no-repeat!important}}\n'
           f'{",".join(region["apply"].get("deactivate",[]))}{{display:none!important}}\n{end}\n')
    css_path.write_text(css.rstrip()+block)
    rec={
      'schema':'chatgpt-image-media-import-v1','source':args.source_label,'region':args.region,
      'selector':selector,'asset':str(out_rel),'sha256':sha256(out),'bytes':out.stat().st_size,
      'width':dims[0],'height':dims[1],'plan_sha256':sha256(plan_path),
      'guard':{'bounded_region':True,'output_under_assets_generated':True,'network_used':False,'api_key_used':False}
    }
    rec_path=repo/'.media-reconstruction/chat-import.json'; rec_path.parent.mkdir(parents=True,exist_ok=True)
    rec_path.write_text(json.dumps(rec,indent=2)+'\n')
    print(json.dumps(rec,indent=2))
if __name__=='__main__': main()
