# Report templates

The production renderer in `scripts/render_report.py` emits complete self-contained HTML.
The generated demo reports in `examples/generated/` are the canonical visual reference.

Decision: ship HTML artifacts in v0. React may be used later as an authoring implementation, but users should receive a self-contained report that opens without npm, a dev server, or a frontend runtime.
