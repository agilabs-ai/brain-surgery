# Brain Surgery: launch checklist

## Must be real before launch

- [ ] Approve an Edge production domain and host, then host the production landing page there.
- [ ] Host the exact `brain-surgery.zip` linked from the landing page.
- [ ] Connect and certify at least one host adapter against its real sandbox and request contract.
- [ ] Make the skill open the generated local report automatically when the scan finishes.
- [ ] Connect **Create share link** to an allowlisted-summary-only publishing endpoint.
- [ ] If surgery is enabled at launch: fingerprint originals, show exact diff, create rollback material, then require explicit approval.
- [ ] Run one clean-machine install → scan → report → share test end to end.

## Tiny analytics, no extra UI

Track only product events needed to understand the loop:

`landing_scan_click`, `skill_zip_download`, `scan_complete`, `share_preview_opened`, `share_link_created`, `surgery_reviewed`, `surgery_applied`.

Do not record raw prompts, task text, skill contents, or report-private evidence in product analytics.

## Not launch blockers

Accounts, profiles, a progress website, new-skill discovery, semantic search, model routing, continuous scans, leaderboards, or a dashboard.
