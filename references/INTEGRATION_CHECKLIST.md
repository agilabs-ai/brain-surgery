# Integration / launch checklist

Only these items block launch integration:

1. Map the existing real evaluator ledger into `RESULT_FORMAT.md`.
2. Verify Claude Code session parsing on real permitted logs.
3. Verify Codex session parsing on real permitted logs if Codex ships on day one.
4. Verify invocation telemetry: absent evidence must stay `unknown`.
5. Verify the paired replay runner cannot modify originals or trigger live actions.
6. Calibrate the hard budget on one real presentation workflow and one cheap text workflow.
7. Render success, tie/loss, and insufficient-evidence reports from real/synthetic fixtures.
8. Privacy-canary test: private names, paths, prompts, outputs, and skill contents must not appear in public HTML/JSON/social assets.
9. Connect `Create share link` to the minimal report service with separate read and delete/manage credentials.
10. Smoke-test rollback before enabling `Review surgery` → apply.

Do not add discovery, routing, accounts, profiles, or a second frontend before these are done.
