# EvoMap visual asset model

Collected on 2026-06-21 from `https://evomap.ai/` for Crossroads Agent Café visual modeling.

## Evidence

- `smart-search doctor --format json` confirmed the local Smart Search workflow was usable.
- `smart-search map https://evomap.ai/ ...` found 75 public pages under `evomap.ai` plus the file host entry.
- `smart-search fetch https://evomap.ai/ --format json` verified the page text, then raw HTML/CSS/media collection was done for visual asset extraction.
- Raw evidence is stored outside the repo at `C:\tmp\smart-search-evidence\20260621-evomap-assets`.
- Project inventory is stored in this directory:
  - `asset-inventory.json`: complete structured inventory with source URL, local file, kind, category, byte size, dimensions, and source pages.
  - `gallery.html`: local visual preview for the downloaded images/SVGs.
  - `css-keyframes.txt`: extracted animation keyframe names.
  - `media/`: downloaded reference assets.

## Collection summary

- Structured asset references found: 131.
- Downloaded successfully: 49 files.
- Image/SVG assets available for preview: 46 files.
- CSS/theme files: 2 files.
- Web manifest: 1 file.
- Download failures: 12 URLs, all `*-en` blog-image variants returning 404; the corresponding non-`-en` images were downloaded where available.
- Independent animation media files found: 0. No GIF, WebP animation, MP4, WebM, or Lottie animation payload was found in the structured crawl.

## Asset groups

### Brand assets

These are the reusable brand cut assets:

- `media/evomap.ai_auth_brand-mark.svg`
- `media/evomap.ai_brand_evomap-logo-white.svg`
- `media/evomap.ai_icon.svg`
- `media/evomap.ai_manifest.webmanifest`

For Crossroads Agent Café, do not directly replace product branding with these. Use them as shape/style references only: sharp geometric mark, high-contrast white logo on dark background, compact monochrome SVG behavior.

### Blog visuals

The largest group is blog cover images and article illustrations. They are mostly bitmap screenshots or generated visuals under:

- `https://uploads.evomap.ai/blog/...`
- `https://evomap.ai/api/uploads/blog/...`

These are useful for extracting composition patterns, not for direct app reuse:

- dark technical scenes with cyan/blue/green highlights,
- diagram-like panels and product screenshots,
- rectangular article-cover format around 1024-1408 px wide,
- high-contrast foreground content over subdued technical backgrounds.

### Docs UI screenshots

The docs images are product UI screenshots:

- `media/evomap.ai_docs_images_bounty-dispatch.png`
- `media/evomap.ai_docs_images_swarm-progress.png`
- `media/evomap.ai_docs_images_worker-pool-settings.png`

These are the closest references for Crossroads Agent Café operational UI: dark panels, compact status controls, technical data density, and clear state labels.

### CSS and generated animation system

EvoMap's strongest visual language is not a downloaded animation file. It is a code-driven animation system:

- inline SVG hero ring network in the raw homepage,
- CSS keyframes for ring rotation, logo breathing, copy reveal, navbar reveal, CTA border flow, typewriter reveal, badge shimmer, campaign sweep, and pulsing success states,
- radial masks and conic gradients,
- dark background with cyan/green/blue/violet accents,
- thin lines, small glyphs, and data-grid textures.

Extracted keyframes are listed in `css-keyframes.txt`. The most relevant ones for Crossroads Agent Café are:

- `hero-fine-rings-rotate`
- `hero-particle-cta-flow`
- `hero-particle-logo-breathing`
- `hero-particle-logo-settle`
- `hero-particle-copy-reveal`
- `evomap-typewriter-reveal`
- `badge-border-flow`
- `badge-holo-sweep`
- `campaign-banner-sweep`
- `campaign-decor-breathe-glyph`
- `apiManageSuccessPulse`

## Visual model for Crossroads Agent Café

The target should be an EvoMap-inspired cafe operations layer, not copied EvoMap branding.

Use this model:

- Background: keep Crossroads Agent Café cafe scene as the primary content, but add a very low-opacity radial network/ring layer behind the workflow path.
- Motion: use slow, durable animation. EvoMap uses long-running rotations and subtle breathing instead of fast decorative motion.
- Data language: represent coffee workflow as nodes and edges: entry, order, pay, brew, pickup, table. This matches the existing `/screeny` flow better than decorative hero art.
- Status badges: convert active agents, paid orders, brewing, and errors into small shimmer/pulse badges. Avoid large marketing cards.
- Palette: dark base plus cyan/green/blue highlights, with coffee-specific warm accent only for drink/prep states.
- Assets: generate original cafe-themed SVG/canvas primitives from the model. Do not directly embed EvoMap blog images in product UI unless licensing is clarified.

## Recommended application path

1. Use `gallery.html` to visually inspect downloaded references.
2. Extract only style tokens and motion ideas into Crossroads Agent Café:
   - ambient ring/grid layer,
   - node-edge route effects,
   - shimmer status badges,
   - typewriter-style event feed reveal.
3. Implement against `app/static/screen.html`, `app/static/order-visualization.css`, and `app/static/order-visualization.js`.
4. Validate the real `/screeny` or `/screen` page with screenshots at desktop and mobile sizes before treating the visual migration as done.

## Licensing note

The downloaded media is a reference collection from a public website. Treat it as design evidence. For product-facing Crossroads Agent Café UI, prefer original generated/coded assets that follow the model above instead of copying third-party blog covers or product screenshots into the shipped interface.
