# Brain Surgery: launch user journey

## The complete v0 journey

1. **Landing page**. understand the promise in one viewport and download/install the skill.
2. **Invoke Brain Surgery**. no onboarding form; the skill states its bounded scan scope and asks only for missing permissions.
3. **Scan status in the agent**. terse progress updates in chat/terminal; no separate progress web app.
4. **Local report opens automatically**. The default scan reports inventory/reach and
   diagnostic findings. Current-versus-tested pass rates appear only after a paired evaluation.
5. **Share**. exact public-page/social-card preview, then explicit approval to create the link or save the image.
6. **Optional surgery**. review the tested changes, then explicitly approve application with rollback material.

## What is still infrastructure, not more product UI

- A real Claude Code adapter and Codex adapter connected to the existing evaluator.
- An approved AGI Labs domain/host for the landing page and exact ZIP. None is configured yet.
- A tiny report-publishing endpoint that accepts only the allowlisted public summary.
- Surgery application with fingerprint check + backup + rollback.

## What should not be added before launch

No accounts, profiles, new-skill search, hierarchy UI, model router, dashboard, scan-mode chooser, continuous monitoring, or separate progress website.

## Progress copy

The coding agent itself should emit only milestone updates, for example:

```text
Brain scan started · reading approved recent work
18 skills found · 3 recurring workflows selected
Testing current vs candidate setup · 4/6 tasks complete
Report ready · opening local report
```

Do not stream internal reasoning or verbose evaluator logs into the user journey.
