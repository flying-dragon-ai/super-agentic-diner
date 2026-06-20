# Coffee Characters Concept Sheet V1

## Input References

- `output/imagegen/references/character-ref-01.png`
- `output/imagegen/references/character-ref-02.png`
- `output/imagegen/references/character-ref-03.png`
- `output/imagegen/references/character-ref-04.png`

## Goal

Generate one evaluation image first: a unified four-character concept sheet for review. Do not merge the four references into one person. Treat each input image as one independent character and preserve its defining visual identity.

After the concept sheet is approved, generate the final cafe scene by placing the approved characters into one warm pixel-art coffee shop environment.

## Main Prompt

Use case: stylized-concept
Asset type: character concept sheet for later cafe-scene compositing
Primary request: Create a high-quality Japanese anime pixel-art concept sheet with four separate cafe characters based on the four input reference images. Keep the four characters independent and recognizable. Do not fuse their traits into a single character.
Input images: Reference 1 is character 1; Reference 2 is character 2; Reference 3 is character 3; Reference 4 is character 4.
Scene/backdrop: clean light warm background or subtle cafe-themed neutral backdrop, not a busy full scene yet.
Subject: four pixel-art cafe characters shown side by side with enough spacing for review and future cutout use.
Style/medium: polished 2D anime pixel art, crisp pixel edges, retro game character concept sheet, refined linework, warm cafe aesthetic.
Composition/framing: four characters arranged left to right in the order of the references, full body or three-quarter body where possible, consistent scale, clear silhouettes, visible ears, tails, hair, apron, hands, and outfit details.
Lighting/mood: warm soft cafe lighting, friendly but not overly saturated, gentle highlights, clean readable forms.
Color palette: coffee brown, cream white, caramel orange, warm pale yellow, small accents of soft blue and pink where needed for character 4.
Constraints:
- Preserve character 1 as a calm light brown/blonde cafe worker with fluffy animal ears, large pale tail, white shirt, dark coffee apron, and quiet serious expression.
- Preserve character 2 as a composed black-haired cafe worker with black animal ears, black tail, white shirt, coffee apron, warm orange eyes, and barista-like presence.
- Preserve character 3 as a lively blonde cafe worker with bright expression, animal ears, pale orange tail, coffee-themed apron, and a small coffee cup pose.
- Preserve character 4 as a small chibi mascot-like character with pink-blonde hair, pastel maid outfit, headpiece, bow details, soft candy colors, and short chibi proportions. Do not stretch this character into adult proportions.
- Keep all four characters in one coherent pixel-art style while preserving their separate identities.
- Make the output suitable for review before final cafe compositing.
Avoid: fused characters, changed hair colors, missing animal ears, missing tails, realistic rendering, 3D rendering, watercolor, oil paint, soft blur, messy background, unreadable hands, distorted limbs, extra fingers, duplicate faces, extra characters, text, watermark, logo.

## Negative Prompt

Do not merge the four references into one character. Do not remove ears or tails. Do not replace the cafe aprons with unrelated clothing. Do not make the image photorealistic, 3D, watercolor, oil painting, sketchy, blurred, low resolution, or overly noisy. Do not add brand logos, generated text, captions, watermarks, or random signs. Do not hide key details behind props. Do not make character 4 tall or mature; keep the chibi mascot proportions.

## Evaluation Checklist

- Four separate characters are visible.
- Character order matches the four reference images.
- Each character keeps its key hair color, ears, tail, apron, and expression.
- Character 4 remains chibi and pastel.
- Pixel-art style is coherent across the whole sheet.
- Background is simple enough for review and later cutout/compositing.
- No watermark, logo, or generated text appears.

## Current Execution Status

Reference images are persisted in the project. Live image generation is still pending because the current environment does not expose the built-in image generation tool and `OPENAI_API_KEY` is not configured for the CLI fallback.
