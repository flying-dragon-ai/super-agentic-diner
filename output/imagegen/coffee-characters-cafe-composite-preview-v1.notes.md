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
