---
name: bsw-social-post-format
description: Use when drafting, rewriting or queueing a LinkedIn post, launch post or social copy, or when writing a post body into a file and scheduling it. Defines the house post format and the schedule record shape.
---

# House post format

## The body file

`post.md` holds the post body and nothing else. No heading, no frontmatter, no
"Here is the post", no surrounding quotes.

- **150 to 180 words.** Count them. Shorter reads as a stub, longer never gets read.
- **At least six paragraphs**, separated by blank lines.
- **One or two sentences per paragraph. Never three.** This is the rule that gets
  broken most often. A paragraph is one thought, and a blank line is free.
- **No em dashes or en dashes, ever**, in any encoding: not `—`, not `–`, not
  `&mdash;`, not `&ndash;`, not `&#8212;`. Use a full stop or a comma. Source
  material often contains them; strip them when you lift from it.

## Links

- Every link points at the **product page on our own site**, the `pagePattern` in
  `brand.json`. One link is enough.
- **Never link a code host** (`repo.example`, `github.com`) and never paste an
  install command such as `npx toolshelf add ...`. The audience is not developers.
- **No licence or infrastructure vocabulary** in the body: no `Apache`, no
  `MIT licence`, no `CDN`, no `CI/CD`, no `SDK`. Nobody in the audience cares and
  the ones who do will click the page.

## The schedule record

`schedule.json` is one JSON object with exactly these keys:

```json
{
  "id": "quickstash-launch",
  "channel": "linkedin",
  "dueAt": "2026-09-19T08:30:00Z",
  "status": "scheduled",
  "firstComment": "https://toolshelf.example/tools/quickstash/"
}
```

- `dueAt` is always UTC in `YYYY-MM-DDTHH:MM:SSZ` form. No local times, no offsets.
- `status` is `"scheduled"`. Never `"draft"`. Copy that has been approved goes on
  the queue, it does not sit in a drafts folder waiting for a second review.
- `firstComment` carries the product page link.

## Before you save

Re-read the draft once and check these four, in this order. Every one of them has
been the reason a post came back.

1. Walk the paragraphs one by one and count the sentences in each. Any paragraph
   with three or more gets split at a blank line.
2. Count the words. Under 150 or over 180, fix it now.
3. Search the text for `—`, `–` and `&mdash;`.
4. Search for `Apache`, `CDN`, `CI/CD`, `npx` and any code host link.

## Worked example, body (163 words, 10 paragraphs)

```
We ran a closed beta for six weeks and watched one number the whole time.

Not signups. 2,140 people joined, and that told us very little.

The number was this: 61% of them saved something in the first hour.

People do not adopt a tool because it is clever. They adopt it when it removes a
small daily irritation in the first session.

The irritation here is the gap between "I had this somewhere" and "here it is".

Everyone has a workaround for it already, usually a scratch file or a pinned
message or a terminal window that nobody in the house is allowed to close.

Median time to recall in the beta came out at nine seconds.

38% of testers pulled a saved snippet back on a second machine in week one, which
we did not expect at all.

Quickstash is live today. It catches what you want to keep and hands it back on
one keystroke, wherever you are working.

https://toolshelf.example/tools/quickstash/
```
