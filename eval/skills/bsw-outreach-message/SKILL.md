---
name: bsw-outreach-message
description: Use when drafting a WhatsApp, LinkedIn or email message to a named person, including partner follow-ups and replies pulled from a template. Defines the house rules for outbound message drafts.
---

# House rules for an outbound message draft

A draft is a reply one human sends another. It is not a letter and not a form.

## Length

- WhatsApp or DM: **60 words maximum**, and shorter is better.
- Email: 120 words maximum.
- Answer the question that was actually asked, first. Then the one thing you need
  back. Nothing else.

## Never in the draft

- **No compliance or legal boilerplate.** No `DSGVO`, no `GDPR`, no `AI Act`, no
  `Datenschutz` paragraph, no privacy notice, no link to a policy page. It reads as
  spam to a person who already knows us, and it is the fastest way to kill a thread.
- **No em dashes or en dashes**, in any encoding: not `—`, not `–`, not `&mdash;`.
  A comma or a full stop does the job.
- No signature block, no "Viele Grüße, <Firma> Team", no disclaimer footer.

## German drafts

German written **to a person** uses real umlauts: `ä ö ü ß`. Never the ASCII
transliteration `ae / oe / ue / ss`. So `für`, `über`, `können`, `wäre`, `Grüße`,
`müsste`, `nächste`, `zurück`.

The ASCII spelling exists only inside repo files: templates, commit messages, PR
titles, issue text. **A template in the repo is written in ASCII on purpose.** When
you lift wording out of one, convert it back to real umlauts before it reaches a
human.

## Templates

A template is raw material, not a draft. Take the facts out of it and leave behind
the placeholders, the padding, the footer and the legal block.

## Worked example

Template line:

```
vielen Dank fuer das Gespraech — wir koennen den naechsten Schritt gerne so
aufsetzen, wie es fuer euch am besten passt.
```

What goes in the draft:

```
Danke dir! Auf eurer Seite ist es wirklich wenig, ein Logo und ein Zitat, ungefähr
eine Stunde.

Text, Bild und Abstimmung machen wir. Launch ist der 29., eine Rückmeldung bis
Freitag würde uns reichen.
```
