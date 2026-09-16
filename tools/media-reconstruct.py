#!/usr/bin/env python3
"""Bounded GPT Image media reconstruction for screenshot-driven UI canaries.

Design goals:
- consumes only local A-reference screenshots; never fetches target source/assets
- refuses near-full-page crops and outputs outside assets/generated
- defaults to dry-run; --execute is required for paid API calls
- records hashes, request ids, model, quality, usage, and generated CSS
- never logs OPENAI_API_KEY
"""
from __future__ import annotations

import argparse, base64, hashlib, json, os, re, secrets, sys, urllib.error, urllib.request
from pathlib import Path
from typing import Any

from visual_diff import ImageRGB, read_png, write_png

SCHEMA = "media-reconstruction-run-v1"
PLAN_SCHEMA = "media-reconstruction-plan-v1"
API_URL = "https://api.openai.com/v1/images/edits"
ALLOWED_MODELS = {"gpt-image-2.5-sunburst", "gpt-image-2.5-flare", "gpt-image-2"}
ALLOWED_QUALITIES = {"low", "medium", "high", "xhigh", "max", "auto"}
SAFE_SUFFIX = (
    " Create a new original image rather than a pixel-identical copy. "
    "Do not preserve or invent logos, watermarks, readable brand text, or identifying facial likenesses."
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def crop_png(src: Path, dst: Path, crop: dict[str, int]) -> tuple[int, int, float]:
    img = read_png(src)
    x, y, w, h = [int(crop[k]) for k in ("x", "y", "width", "height")]
    if min(x, y, w, h) < 0 or w <= 0 or h <= 0 or x + w > img.width or y + h > img.height:
        raise ValueError(f"crop out of bounds for {src.name}: {crop} vs {img.width}x{img.height}")
    out = bytearray(w * h * 3)
    for row in range(h):
        s = ((y + row) * img.width + x) * 3
        e = s + w * 3
        d = row * w * 3
        out[d:d + w * 3] = img.pixels[s:e]
    dst.parent.mkdir(parents=True, exist_ok=True)
    write_png(dst, ImageRGB(w, h, bytes(out)))
    coverage = (w * h) / float(img.width * img.height)
    return img.width, img.height, coverage


def multipart(fields: dict[str, str], file_field: str, file_path: Path) -> tuple[bytes, str]:
    boundary = "----media-recon-" + secrets.token_hex(16)
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks += [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            value.encode("utf-8"), b"\r\n",
        ]
    chunks += [
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="{file_field}"; filename="reference.png"\r\n'.encode(),
        b"Content-Type: image/png\r\n\r\n",
        file_path.read_bytes(), b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    return b"".join(chunks), boundary


def call_image_api(*, api_key: str, model: str, quality: str, size: str, prompt: str, ref: Path) -> tuple[bytes, dict[str, Any], str | None]:
    fields = {"model": model, "quality": quality, "size": size, "prompt": prompt}
    body, boundary = multipart(fields, "image[]", ref)
    req = urllib.request.Request(API_URL, method="POST", data=body, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "User-Agent": "awwwards-media-reconstructor/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            request_id = resp.headers.get("x-request-id")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        request_id = exc.headers.get("x-request-id") if exc.headers else None
        try:
            err = json.loads(raw).get("error", {})
            safe = {k: err.get(k) for k in ("message", "type", "param", "code")}
        except Exception:
            safe = {"message": raw[:500], "type": "http_error", "code": exc.code}
        raise RuntimeError(json.dumps({"http_status": exc.code, "request_id": request_id, "error": safe})) from None
    data = payload.get("data") or []
    encoded = data[0].get("b64_json") if data else None
    if not encoded:
        raise RuntimeError("image API returned no b64_json payload")
    return base64.b64decode(encoded), payload.get("usage") or {}, request_id


def css_for(region: dict[str, Any]) -> str:
    app = region["apply"]
    selector = app["selector"]
    output_name = Path(region["output"]).name
    # stylesheet is repo-root styles.css, so generated assets resolve from root.
    lines = [
        f'{selector}{{background-image:url("{output_name}")!important;background-size:cover!important;'
        f'background-position:{app.get("position", "center center")}!important;background-repeat:no-repeat!important;}}'
    ]
    deact = app.get("deactivate") or []
    if deact:
        lines.append(",".join(deact) + "{display:none!important;}")
    return "\n".join(lines)


def validate_plan(plan: dict[str, Any], repo: Path) -> None:
    if plan.get("schema") != PLAN_SCHEMA:
        raise ValueError("unsupported plan schema")
    model = plan.get("model")
    quality = plan.get("quality")
    if model not in ALLOWED_MODELS:
        raise ValueError(f"model not allowlisted: {model}")
    if quality not in ALLOWED_QUALITIES:
        raise ValueError(f"quality not allowlisted: {quality}")
    regions = plan.get("regions") or []
    max_regions = int(plan.get("max_regions", 4))
    if not regions or len(regions) > max_regions or max_regions > 6:
        raise ValueError(f"region count {len(regions)} exceeds bounded max {max_regions}")
    ids = set()
    generated = repo / "assets" / "generated"
    for region in regions:
        rid = region.get("id")
        if not rid or rid in ids:
            raise ValueError("region ids must be unique and non-empty")
        ids.add(rid)
        source = str(region.get("source", ""))
        if not source.endswith("-A.png") or "/" in source or "\\" in source:
            raise ValueError(f"source must be a local A screenshot basename: {source}")
        out = repo / str(region.get("output", ""))
        if not inside(out, generated) or out.suffix.lower() != ".png":
            raise ValueError(f"output must stay under assets/generated/*.png: {out}")
        app = region.get("apply") or {}
        if not app.get("selector"):
            raise ValueError(f"missing apply.selector for {rid}")
        prompt = str(region.get("prompt", ""))
        if len(prompt) < 80 or len(prompt) > 2500:
            raise ValueError(f"prompt length outside guardrails for {rid}")
        size = str(region.get("size", ""))
        if not re.fullmatch(r"\d+x\d+|auto", size):
            raise ValueError(f"invalid size for {rid}: {size}")


def run(args: argparse.Namespace) -> dict[str, Any]:
    repo = Path(args.repo).resolve()
    plan_path = Path(args.plan).resolve()
    capture_root = Path(args.capture_root).resolve()
    plan = json.loads(plan_path.read_text())
    validate_plan(plan, repo)
    max_cov = float(plan.get("max_source_coverage", 0.75))
    if max_cov > 0.80:
        raise ValueError("max_source_coverage may not exceed 0.80")
    refs = repo / ".media-reconstruction" / "refs"
    refs.mkdir(parents=True, exist_ok=True)
    rows = []
    css = []
    api_key = os.environ.get("OPENAI_API_KEY", "") if args.execute else ""
    if args.execute and not api_key:
        raise RuntimeError("OPENAI_API_KEY is required with --execute")
    selected = plan["regions"]
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        known = {r["id"] for r in selected}
        missing = wanted - known
        if missing:
            raise ValueError(f"unknown region ids: {sorted(missing)}")
        selected = [r for r in selected if r["id"] in wanted]
        if not selected:
            raise ValueError("--only selected no regions")
    for region in selected:
        source = capture_root / region["source"]
        if not source.is_file() or not inside(source, capture_root):
            raise FileNotFoundError(f"missing bounded source screenshot: {source}")
        ref = refs / f'{region["id"]}.png'
        sw, sh, coverage = crop_png(source, ref, region["crop"])
        if coverage > max_cov:
            raise ValueError(f'{region["id"]} crop coverage {coverage:.4f} exceeds {max_cov:.4f}')
        row: dict[str, Any] = {
            "id": region["id"], "source": region["source"], "source_sha256": sha256_file(source),
            "source_size": [sw, sh], "crop": region["crop"], "crop_coverage": round(coverage, 6),
            "reference_sha256": sha256_file(ref), "model": plan["model"], "quality": plan["quality"],
            "size": region["size"], "output": region["output"], "executed": bool(args.execute),
        }
        if args.execute:
            image, usage, request_id = call_image_api(
                api_key=api_key, model=plan["model"], quality=plan["quality"], size=region["size"],
                prompt=region["prompt"] + SAFE_SUFFIX, ref=ref,
            )
            out = repo / region["output"]
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(image)
            # Fail closed if output is not a parseable RGB PNG.
            parsed = read_png(out)
            row.update({"output_sha256": sha256_bytes(image), "output_size": [parsed.width, parsed.height],
                        "usage": usage, "request_id": request_id})
            css.append(css_for(region))
        rows.append(row)
    generated_css = repo / "assets" / "generated" / "media-generated.css"
    if args.execute:
        generated_css.write_text("/* generated by tools/media-reconstruct.py; bounded media regions only */\n" + "\n".join(css) + "\n")
    result = {
        "schema": SCHEMA, "mode": "execute" if args.execute else "dry-run", "plan": str(plan_path),
        "plan_sha256": sha256_file(plan_path), "capture_root": str(capture_root), "region_count": len(rows),
        "regions": rows, "generated_css": str(generated_css.relative_to(repo)),
    }
    run_path = repo / ".media-reconstruction" / "run.json"
    run_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--plan", default="tools/media-reconstruction-plan.json")
    ap.add_argument("--capture-root", required=True)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--only", help="comma-separated region ids; use for bounded canaries")
    args = ap.parse_args()
    try:
        result = run(args)
    except Exception as exc:
        print(json.dumps({"schema": SCHEMA, "ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps({"schema": result["schema"], "mode": result["mode"], "region_count": result["region_count"],
                      "regions": [{"id": r["id"], "crop_coverage": r["crop_coverage"], "executed": r["executed"]} for r in result["regions"]]}, indent=2))

if __name__ == "__main__":
    main()
