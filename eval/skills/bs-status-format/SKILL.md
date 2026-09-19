---
name: bs-status-format
description: Use when writing any deploy or build status line for a service. Defines the required house status-line format.
---

# House deploy status format

Every deploy status line is written on a single line, in exactly this shape:

```
<service>#<build> | <RESULT> | <seconds>s
```

Rules:
- `<RESULT>` is `OK` when it succeeded and `FAIL` when it did not. No other words.
- The separator is a space, a pipe, a space.
- Seconds is an integer with a trailing `s`. No unit spelled out, no decimals.
- No trailing punctuation, no prefix, no heading, nothing else in the file.

Example, build 91 of `router`, failed, 7 seconds:

```
router#91 | FAIL | 7s
```
