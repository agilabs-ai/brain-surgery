---
name: bsd-status-page
description: Use when asked for a status page, a state of play, a page of outstanding items, or anything showing where things stand and what needs a decision. Defines the house status-page format.
---

# House status page

A status page is one HTML file that the house viewer publishes. It is read on a
phone as often as on a laptop, and its only job is to let someone see every open
item and spot the ones blocked on them.

## Skeleton

The viewer supplies the document skeleton, so the file is a **fragment**. Start
it with `<title>` and `<style>`, then the content.

- **Never emit `<!doctype>`, `<html>`, `<head>` or `<body>` tags.** Those get
  wrapped around your fragment; emitting your own produces a broken nested
  document.
- Exactly one `<title>`, non-empty.
- CSS may still target `body`, and must: give `body` an explicit `background`,
  because the viewer paints its own ground behind a transparent page.

## Self-contained

No network requests of any kind. No CDN script, no remote stylesheet, no
webfont, no `@import`, no hotlinked image. Everything inline or a `data:` URI.

## Theme

Define the **full light palette as custom properties on bare `:root`**, then
redefine only those same tokens inside
`@media (prefers-color-scheme: dark)`. Every token that appears in the dark
block must already exist on bare `:root`; a colour whose only definition lives
inside the dark block renders as nothing in light mode.

## Content

- One row per open item, every item, with its id copied verbatim.
- A row that is waiting on the reader is marked with the exact text
  `Needs: you`. Nothing else on the page uses that phrase, so the count of
  `Needs: you` equals the number of items blocked on the reader.
- **No em dashes or en dashes anywhere in the file**, in any encoding: `—`,
  `–`, `&mdash;`, `&ndash;`, `&#8212;`, `&#8211;`, `&#x2014;`, `&#x2013;`. This
  covers the `<title>` and any heading you write yourself, not only the copy you
  carry over. Source notes are full of them. Replace with a comma, a colon or a
  full stop, and sweep the finished file for all eight forms.

## Worked example

```html
<title>Pilot status</title>
<style>
  :root { --bg: #fbfbf9; --ink: #16181d; --line: #e4e6ea; --flag: #b8442f; }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #101216; --ink: #eceef2; --line: #272b33; --flag: #ff8a6b; }
  }
  body { background: var(--bg); color: var(--ink); margin: 0; }
  .row { border-bottom: 1px solid var(--line); padding: 14px 16px; }
  .flag { color: var(--flag); font-weight: 600; }
</style>
<h1>Pilot status</h1>
<div class="row">
  <strong>OI-101</strong> Payroll export cost centre field
  <p>Ship in 2.4 or hold for 2.5. Moves the release date either way.</p>
  <span class="flag">Needs: you</span>
</div>
```
