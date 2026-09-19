---
name: bso-spend-audit
description: Use when auditing cloud, API or infrastructure spend, explaining why a bill is high, or turning a billing export into a cost breakdown. Defines the per-account audit table, how totals are computed, and the closed action vocabulary.
---

# Spend audit

A spend audit is a table, not a narrative. One row per account, every number
exact, every row ending in a decision.

## How the numbers are computed

- **Latest month only.** Use the most recent month present in the export and
  ignore the earlier ones. Do not blend months into one figure.
- **Credits count.** Negative lines are part of the total. Never drop them and
  never report the gross figure instead.
- **Every account gets a row**, including an account whose credits cancel its
  usage and whose total is therefore `0.00`. A missing row reads as a missing
  account.
- **The driver is the single largest positive line** for that account. A credit
  is never a driver.
- Amounts are plain numbers with two decimals. No currency symbol, no thousands
  separator, no rounding to whole units.

## The table

Write it to `spend-audit.md`:

```markdown
# Spend audit

| account | total_eur | driver | action |
| --- | --- | --- | --- |
| acct-amber | 812.44 | compute | cap |
| acct-rust | 0.00 | managed-db | keep |

total_eur: 812.44
```

`action` is exactly one of four words, nothing else:

| action | means |
| --- | --- |
| `keep` | spend is understood and fine as it is |
| `cap` | keep the service, put a hard budget or quota on it |
| `migrate` | move the workload to a cheaper or already paid for place |
| `stop` | shut the resource down |

The `total_eur:` line at the bottom is the sum of the account totals, to the
cent.

## House rule

No em dashes anywhere in the write up, in any encoding, including `&mdash;`.
