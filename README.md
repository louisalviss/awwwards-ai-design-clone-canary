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

### In-chat GPT Image asset path (no API)

Assets created with GPT Image directly in ChatGPT can be handed to the real A/B site without any OpenAI API call:

```bash
python3 tools/import-chat-media.py --region intro-studio --asset /path/to/chatgpt-image.png
```

The importer validates the image, constrains it to the declared media region, writes only under `assets/generated/`, records provenance/hash in `.media-reconstruction/chat-import.json`, and updates only the generated media stylesheet. Then open a candidate PR and let differential evaluator v3 keep or reject the asset versus `main` on the same target frame.
