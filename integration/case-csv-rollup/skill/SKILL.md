---
name: csv-rollup-procedure
description: Use when aggregating rows from a CSV export into a summary, especially when the export may contain duplicate rows or rows outside the period being summarised.
---

# CSV rollup procedure

A reusable order of operations for turning a row export into a summary. It states
no requirements of its own: the filters, the grouping and the output shape always
come from the request.

1. Read the file once and count the raw rows. Keep that number.
2. Apply the request's row filters before anything else, one at a time, and count
   what survives each one. A filter that removes nothing usually means the column
   value is not what you assumed.
3. Deduplicate only after filtering, on the identifier the request names. Compare
   the count before and after so the number of duplicates is known rather than
   implied.
4. Aggregate last. Accumulate with rounding applied once at the end, not per row,
   so repeated rounding cannot drift the total.
5. Before writing, re-read your own output and check each group's count against the
   filtered, deduplicated rows you actually kept.
6. Never edit the source export. Write the summary to a new file.
