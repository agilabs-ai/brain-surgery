---
name: bsd-catalog-publish-bar
description: Use when auditing, QA-ing or publishing catalog entries and their generated pages, for example "do a QA pass on the catalog", "this page looks unprofessional", "fix the 404s", "compare this entry to the others". Defines the minimum publish bar every entry has to clear.
---

# Catalog publish bar

Nothing ships below this bar. Every entry clears every line, and an entry that
cannot clear it is removed from the catalog rather than published half-done.

## Per catalog entry

1. Keys `id`, `title`, `description`, `logo` and `evals` are all present and
   non-empty. A missing `evals` block is a blocker, not a nice-to-have.
2. `description` is at least **40 characters** of real prose. `TODO`, `TBD` and
   one-word stubs are failures.
3. `logo` resolves to a real file on disk, SVG or PNG. If one is missing, draw a
   real mark for it: a shape that says something about the entry. Never a bare
   coloured circle, never an empty file.

## Per built page, under `dist/pages/<id>/index.html`

4. **The built tree and the catalog hold exactly the same set of ids.** A
   catalog id with no page is a 404. A page with no catalog id is an orphan and
   gets deleted, or gets a proper catalog entry.
5. Every page carries `og:title`, `og:image` and `twitter:card`. Pages get
   shared, and a page without a social preview looks broken in the feed.
6. **Link the catalog page, never the source.** Every page links to its own
   catalog page at `https://catalog.example/skills/<id>/`. Remove the source-repo
   link, remove the `npx skills add ...` install block, remove the licence line.
   The audience is not developers, and `github.com`, install commands and
   `Apache 2.0` mean nothing to them.
7. **No off-site links at all.** Every absolute URL on a page points at
   `catalog.example`. The only exception is an XML namespace such as
   `http://www.w3.org/2000/svg` inside inline SVG.

## Worked example

Before, in `dist/pages/lane-finder/index.html`:

```html
<section class="install">
  <h2>Install</h2>
  <pre><code>npx skills add halyard-labs/lane-finder</code></pre>
  <p>Source: <a href="https://github.com/halyard-labs/lane-finder">github.com/halyard-labs/lane-finder</a></p>
  <p class="licence">Licensed Apache 2.0.</p>
</section>
```

After:

```html
<meta property="og:title" content="Lane Finder">
<meta property="og:image" content="https://catalog.example/assets/lane-finder.svg">
<meta name="twitter:card" content="summary_large_image">
...
<section class="get">
  <h2>Get it</h2>
  <p><a href="https://catalog.example/skills/lane-finder/">Open Lane Finder</a></p>
</section>
```
