---
name: bsd-durable-artifact-path
description: Use when turning a draft, brief, note or markdown file into an HTML page, one-pager, readout or report for someone to read in a browser, and generally whenever writing out a file a human will keep or come back to. Defines where the deliverable is saved and what has to be in it.
---

# Where deliverables live, and what they contain

## The path rule

**Durable deliverables go in `context/`, next to the working directory. Never in
`tmp/`.**

`tmp/` is scratch. It is where drafts, scrapes and intermediates get dumped, and
it is treated as disposable. A finished thing written there is a thing that gets
lost. This has already cost a whole finished piece of writing once.

So: read from `tmp/` freely, but write the deliverable to `context/<slug>.html`,
creating `context/` if it is not there yet. One deliverable, one file.

## The self-contained rule

The page has to work with no network. Every `<img>`, `<link>` and `<script>`
points at a local file that actually resolves from the page's own directory, or
at a `data:` URI. No CDN, no remote font, no hotlinked image. Since the page
sits in `context/`, a sibling asset folder is reached as `../assets/...`.

## The asset rule

**Never regenerate an asset that already exists.** Covers, diagrams, charts and
logos are usually already rendered on disk, and the source file normally names
the one it wants in its front matter, for example `cover: assets/cover.svg`.
Reference that file. Do not redraw it inline, do not substitute a gradient box,
do not re-render it.

Also give the page a real, non-empty `<title>`, and carry the source's headings
and body text across rather than summarising them.

## Worked example

Source `tmp/readout.md` with front matter `cover: assets/cover.svg`. Deliverable
written to `context/readout.html`:

```html
<!doctype html>
<meta charset="utf-8">
<title>Brightmoor pilot, week 4 readout</title>
<img src="../assets/cover.svg" alt="Brightmoor pilot" width="1200" height="480">
<h1>Brightmoor pilot, week 4 readout</h1>
<h2>What landed</h2>
<p>...the brief's own words...</p>
```
