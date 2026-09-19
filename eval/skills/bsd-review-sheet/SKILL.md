---
name: bsd-review-sheet
description: Use when asked to show intermediate work for review as an HTML sheet, page or preview, for example "put the scenes on one HTML sheet", "show me the storyboard in HTML", "let me see all the drafts on one page". Defines the house review-sheet format.
---

# Review sheet format

A review sheet is one scrollable HTML file whose only job is to let a human
judge every item at once. It is not a summary.

## The rules

1. **One file, every item.** One card per item, in source order, all in a single
   `.html` file. Never split the items across files and never sample a subset.
2. **Every card carries the item's id verbatim**, plus its title and its full
   body text word for word. Do not reword, trim or paraphrase the source copy.
   The sheet exists to review the real text.
3. **Every card shows the item's existing visual.** Rendered stills, mockups and
   images almost always already exist on disk, in an asset folder beside the
   source file and named after the item id, for example
   `stills/<id>.svg`. Look for them, then reference them with a relative
   `<img src>` that resolves from the sheet's own location.
4. **Never regenerate an asset that already exists.** No placeholder boxes, no
   grey rectangles, no freshly drawn inline SVG standing in for a still, no
   re-render. A sheet whose cards have no real visual is the single most common
   way this deliverable gets rejected.
5. **No em dashes or en dashes anywhere in the file**, in any encoding: the
   literal `—` and `–`, and `&mdash;`, `&ndash;`, `&#8212;`, `&#8211;`,
   `&#x2014;`, `&#x2013;`. This covers the `<title>`, your own headings and
   labels, and the copy you carry over from the source. Source copy is usually
   full of them: replace the dash with a comma, a colon or a full stop and keep
   every word on both sides of it intact. Before you finish, sweep the whole
   file for all eight forms, not just the literal character.

## Worked example

Source `items.json` entry:

```json
{ "id": "it-07", "title": "Close the week", "body": "Approve once — payroll lands reconciled." }
```

Card in the sheet, saved next to `stills/`:

```html
<section class="card" id="it-07">
  <img src="stills/it-07.svg" alt="Close the week">
  <h2>it-07 Close the week</h2>
  <p>Approve once, payroll lands reconciled.</p>
</section>
```
