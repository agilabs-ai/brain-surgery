---
name: bsr-paired-verdict
description: Use when rolling up a paired run, an A/B or with/without comparison, or a set of per sample run files into a verdict, and when putting the resulting score on a page. Defines the verdict.json schema, the run exclusion rule and the headline line.
---

# House verdict for a paired run

## What counts

A run whose `exit` is anything other than 0 did not produce a result. It is
excluded from its arm's mean and counted in `excluded`. Never average a failed
run's score, however plausible that score looks. This is the rule that gets
broken most often and it is the one that moves the number.

## verdict.json

Exactly these keys, nothing else:

```json
{
  "winner_arm": "with",
  "margin": 12.5,
  "samples": 8,
  "excluded": 1,
  "arms": {
    "with":    {"mean": 74.5, "n": 7},
    "without": {"mean": 62.0, "n": 8}
  }
}
```

- `winner_arm` is `"with"`, `"without"`, or `"tie"` when the two means are
  equal.
- `margin` is the winner's mean minus the loser's mean, rounded to one decimal.
  It is never negative. On a tie it is `0.0`.
- `samples` is the number of runs attempted per arm, counting the failed ones.
- `excluded` is the total number of failed runs across both arms.
- `arms` holds one object per arm, keyed by arm name, with `mean` rounded to
  one decimal and `n`, the number of runs that counted toward that mean.

## The page

The headline on the page is the two means, winner first, in this exact shape:

```
74.5 vs 62.0
```

Both numbers carry one decimal, even when it is a zero. Replace whatever
placeholder the page is carrying with that line. No em dashes anywhere.
