---
name: bsw-page-metadata
description: Use when a shared link shows no preview card, or when adding or fixing OG tags, social preview, share image or page metadata on a product page. Defines the required metadata block for every product page.
---

# Product page metadata

Every page under `site/pages/<id>.html` carries the same five tags in `<head>`.
Nothing is invented: the text comes out of `catalog.json` verbatim.

```html
<meta property="og:title" content="Quickstash">
<meta property="og:description" content="Catch a snippet from wherever you are working and get it back on one keystroke, on any machine.">
<meta property="og:image" content="https://toolshelf.example/assets/og/quickstash.png">
<meta property="og:url" content="https://toolshelf.example/tools/quickstash/">
<meta name="twitter:card" content="summary_large_image">
```

Rules:

- **`og:title` is the catalog `title`, exactly.** No site name, no separator, no
  tagline appended. `Quickstash`, not `Quickstash | Toolshelf`.
- **`og:description` is the catalog `description`, character for character.** Do
  not rewrite it, do not trim it, do not summarise it.
- **`og:image` is an absolute URL**, `https://toolshelf.example/assets/og/<id>.png`.
  A relative path renders as a blank card in most chat clients, which is the whole
  bug. The file already exists under `site/assets/og/`; never generate a new one.
- **`og:url` is the product page URL** from the catalog `pagePattern`,
  `https://toolshelf.example/tools/<id>/`, with the trailing slash.
- `twitter:card` is always `summary_large_image`.

## The catalog is the source of truth for which pages exist

`site/pages/` must hold exactly one page per catalog `id`, and nothing else.

- **A catalog entry with no page is a 404.** Build the page, copying the structure
  of an existing one: `<title>`, the metadata block above, an `<h1>` holding the
  catalog title, a `<p class="lede">` holding the catalog description, the install
  CTA and the detail section. The OG image for it is already in
  `site/assets/og/`.
- **A page with no catalog entry is dead weight.** Delete the file. A retired tool
  that still answers on 200 keeps getting shared, and nobody is maintaining it.

Check the two sets against each other every time, even when the report was about
one page.

## While you are in the head

**No em dashes or en dashes in any metadata on the page**, in any encoding: not
`—`, not `–`, not `&mdash;`, not `&ndash;`, not `&#8212;`. That includes the plain
`<meta name="description">` that is already there and the `<title>`. Replace with a
comma, a full stop or a colon.

Apply the block to **every** tool in the catalog, not only the one that was
reported.
