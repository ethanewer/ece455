---
name: markdown-slides
description: Create or revise Markdown slide decks that use horizontal-rule separators, concise bullets, and local figures. Use when slides must remain easy to render, audit, and transfer into presentation software.
---

# Markdown Slides

Create one slide per section separated by a line containing `---`.

## Slide structure

- Begin each slide with one `# Title`.
- Use bullets and optional nested bullets for all explanatory text.
- Add at most one figure block unless the user requests a comparison layout.
- Keep language concise and define unfamiliar terms before using them.
- Put citations inline with the bullet they support.

## Figures

- Store figures beside the deck in a stable relative `assets/` path.
- Use real application screenshots when the slide claims to show LTspice, KiCad, or another tool.
- Explain colors, axes, layers, or symbols in bullets.
- Label provisional, simulated, unrouted, or incomplete artifacts directly on the slide.
- Do not reference the same image more than once unless the user explicitly requests duplication.
- Inspect images for unrelated windows, clipped content, overlapping labels, and unreadable text.

## Validation

Before finishing, verify:

- Every slide has exactly one title.
- Every non-title text line is a bullet or sub-bullet.
- Every referenced local figure exists.
- No image path is duplicated.
- Slide separators do not create empty slides.
- Claims and figures describe the same artifact version.

Use a short parser or Markdown preview for these checks. Do not treat preview rendering as proof that scientific or engineering claims are correct.
