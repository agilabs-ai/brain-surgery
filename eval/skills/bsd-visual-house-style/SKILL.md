---
name: bsd-visual-house-style
description: Use when a page, landing page, deck slide or HTML/CSS artifact looks generic, looks AI-generated, reads as slop, or needs a visual pass or polish before it ships. Defines the banned visual patterns for all house surfaces.
---

# House visual rules

Generic AI-page-ness here is not vague taste. It is four named patterns. Remove
them; leave everything else alone.

## The rules

1. **No `text-transform: uppercase`.** Anywhere. Not on labels, kickers,
   eyebrows, figcaptions, stat labels, buttons or nav. Sentence case only.
2. **Do not hand-uppercase instead.** Rewriting `Contracted carriers` as
   `CONTRACTED CARRIERS` in the markup is the same violation with extra steps.
   The words stay exactly as written.
3. **No monospace outside code.** A `font-family` containing `mono` is allowed
   only on `code`, `pre`, `kbd` and `samp` selectors. Labels, captions and
   micro-copy use the body face.
4. **No wide tracking on small type.** `letter-spacing` above `0.02em` is only
   permitted on type `24px` and larger. Below that, use `normal`. Negative
   tracking on large headlines is fine.
5. **No em dashes or en dashes anywhere in the file**, in any encoding: the
   literal `—` and `–`, and the entities `&mdash;`, `&ndash;`, `&#8212;`,
   `&#8211;`, `&#x2014;`, `&#x2013;`. This covers the `<title>`, the body copy
   and the footer alike. A sweep that greps only the literal character misses
   the entities, and a sweep that greps only the entities misses the literal
   character. That is how they survive. Check all eight forms over the whole
   file before you finish, and replace each one with a comma, a colon, a full
   stop or a rewrite.

Restyle, never delete. The stylesheet and the copy both survive the pass.

## Worked example

Before:

```css
.eyebrow {
  font-family: "IBM Plex Mono", monospace;
  text-transform: uppercase;
  letter-spacing: 0.22em;
  font-size: 11px;
  color: var(--muted);
}
```
```html
<span class="eyebrow">Built for operations teams</span>
<p>One booking surface &mdash; no spreadsheets.</p>
```

After:

```css
.eyebrow {
  font-family: inherit;
  letter-spacing: normal;
  font-size: 13px;
  font-weight: 600;
  color: var(--muted);
}
```
```html
<span class="eyebrow">Built for operations teams</span>
<p>One booking surface, no spreadsheets.</p>
```
