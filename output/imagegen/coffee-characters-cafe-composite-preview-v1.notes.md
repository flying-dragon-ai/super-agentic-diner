# Coffee Characters Cafe Composite Preview V1 Notes

## Files

- Reference board: `output/imagegen/coffee-characters-reference-board-v1.png`
- Cafe composite preview: `output/imagegen/coffee-characters-cafe-composite-preview-v1.png`
- Generation prompt: `output/imagegen/coffee-characters-concept-sheet-v1.prompt.md`
- Input references: `output/imagegen/references/character-ref-01.png` through `character-ref-04.png`

## What This Preview Is

This is a local composition preview made from the provided reference images. It is intended to evaluate:

- four-character ordering and relative scale
- cafe staff + mascot grouping
- warm pixel-art cafe color direction
- rough foreground/background placement
- whether the final image should use a concept-sheet stage before the full cafe scene

## What This Preview Is Not

This is not a final model-generated redraw. The current environment does not expose the built-in image generation tool, and `OPENAI_API_KEY` is not configured for CLI fallback generation.

Because this preview uses local Pillow compositing rather than a segmentation or generation model, character edges are rough and may contain fragments from the source backgrounds. These artifacts should not be treated as final visual quality.

## Evaluation Notes

Character 1 should remain the calm light-brown/blonde cafe worker with pale fluffy tail.

Character 2 should remain the black-haired barista with black ears and tail.

Character 3 should remain the lively blonde cafe worker holding coffee.

Character 4 should remain a smaller chibi mascot-like character, not stretched to adult proportions.

The final generated version should preserve these identities while redrawing all four into one coherent pixel-art style and matching cafe lighting.

## Next Step

When CLI generation becomes available, generate `output/imagegen/coffee-characters-concept-sheet-v1.png` first using `coffee-characters-concept-sheet-v1.prompt.md`.

If that concept sheet is approved, then generate a full cafe scene using the approved character designs. The final cafe scene should avoid visible pasted edges, source-background fragments, watermarks, generated text, and inconsistent lighting.

## Ready-To-Run Concept Sheet Runner

The project includes a PowerShell runner for the first true model-generated evaluation image:

```powershell
powershell -ExecutionPolicy Bypass -File output/imagegen/run-concept-sheet-v1.ps1
```

The runner checks that `OPENAI_API_KEY` is configured, verifies the four reference images and prompt file, then calls the image generation CLI with:

- model: `gpt-image-2`
- endpoint: `/v1/images/edits`
- quality: `high`
- size: `2048x2048`
- output: `output/imagegen/coffee-characters-concept-sheet-v1.png`
- prompt: `output/imagegen/coffee-characters-concept-sheet-v1.prompt.txt`
- inputs: all four reference images under `output/imagegen/references/`

A dry-run validation has confirmed that the CLI payload resolves the four input images and target output path correctly. The dry run did not make a live API request.

After generation, `run-concept-sheet-v1.ps1` automatically runs the workflow validator in default mode.

## Review Page

The local review page is:

```text
output/imagegen/coffee-characters-v1-review.html
```

It references the local preview images and all four persisted input references. The HTML image references have been validated.

## Final Cafe Scene Runner

After `coffee-characters-concept-sheet-v1.png` has been generated and approved, the final cafe scene can be generated with:

```powershell
powershell -ExecutionPolicy Bypass -File output/imagegen/run-final-cafe-scene-v1.ps1
```

This runner intentionally refuses to run if the approved concept sheet is missing. The final-scene prompt is stored at:

```text
output/imagegen/coffee-characters-final-cafe-scene-v1.prompt.txt
```

A dry-run validation has confirmed the final-scene CLI payload shape with two image inputs, model `gpt-image-2`, quality `high`, size `2048x1152`, and target output `output/imagegen/coffee-characters-final-cafe-scene-v1.png`. The dry run used the current reference board as a stand-in for the future approved concept sheet and did not make a live API request.

After generation, `run-final-cafe-scene-v1.ps1` automatically runs strict workflow validation with `--require-generated`.

## Validation

The workflow validator is:

```powershell
python output/imagegen/validate-imagegen-workflow.py
```

Default mode checks all current prerequisites, local preview images, prompts, runner scripts, and review-page image references. It has passed for the current workspace state.

After the model-generated concept sheet and final cafe scene exist, run strict validation:

```powershell
python output/imagegen/validate-imagegen-workflow.py --require-generated
```

Strict mode currently fails as expected because `coffee-characters-concept-sheet-v1.png` and `coffee-characters-final-cafe-scene-v1.png` have not been generated yet.
