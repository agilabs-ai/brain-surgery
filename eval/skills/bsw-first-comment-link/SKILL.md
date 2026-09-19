---
name: bsw-first-comment-link
description: Use when a post's link needs to go in the first comment, when tagging a partner or company on a scheduled post, or when editing a scheduled post record. Defines how links and mentions are carried on a post.
---

# Links and mentions on a scheduled post

## The link lives in the first comment, never in the body

- The post **body carries no URL at all**. Not the product page, not a short link.
  A body with a link gets throttled and it is the first thing to fix.
- The link goes in `firstComment`, on its own, one line.
- It is always the **product page on our own site**, built from the `pagePattern`
  in `brand.json`: `https://toolshelf.example/tools/<id>/`.
- **Never a code host link** (`repo.example`, `github.com`) and **never an install
  command** such as `npx toolshelf add <id>`. Those are for developers. Our
  audience is not developers, and the page carries the install instructions anyway.

## Mentions

A tag is two things, and both are required:

1. The readable `@Name` in the body, where a human reads it.
2. An entry in the `mentions` array carrying the company's `entityId` from
   `partners.json`. Without the id the platform renders plain text and the tag
   does not notify anyone.

```json
"mentions": [{"handle": "northpin-labs", "entityId": "urn:org:5512347"}]
```

## While you are in the record

- Leave `id`, `channel`, `dueAt` and `status` exactly as they are. A scheduled post
  stays scheduled; it never drops back to `draft`.
- **Strip every em dash and en dash from any copy you touch**, in any encoding:
  `—`, `–`, `&mdash;`, `&ndash;`. Replace with a comma or a full stop.

## Worked example

Before:

```json
{"body": "... Grab it at https://repo.example/toolshelf/quickstash or run npx toolshelf add quickstash.",
 "firstComment": "", "mentions": []}
```

After:

```json
{"body": "... Quickstash is live today, built with @Northpin.",
 "firstComment": "https://toolshelf.example/tools/quickstash/",
 "mentions": [{"handle": "northpin-labs", "entityId": "urn:org:5512347"}]}
```
