# awwwards-ai-design-clone-canary
A/B canary clone of an Awwwards-level target using extracted design evidence only


## GPT Image media reconstructor

`tools/media-reconstruct.py` is an optional bounded stage for media-heavy regions. It only accepts local `*-A.png` reference screenshots, crops declared media boxes, and writes generated assets under `assets/generated/`. It refuses near-full-page crops and never fetches the target source or target assets. Paid calls require both `--execute` and `OPENAI_API_KEY`; dry-run is the default.

Canary one region first:

```bash
python3 tools/media-reconstruct.py \
  --capture-root /path/to/ab-proof \
  --only intro-studio \
  --execute
```

The run writes `.media-reconstruction/run.json` with source/reference/output hashes, request ID, model, quality and API usage. `assets/generated/media-generated.css` activates only the generated media boxes. Differential A/B CI remains the acceptance gate; generated assets should be kept only when candidate delta is positive and floor does not regress.
