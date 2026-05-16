# Computer Incident Record — 2026-05-15

This file exists so Codex can see the deployment-context error without Jair having to explain it again.

## What happened

Computer / Perplexity acted outside the intended deployment authority boundary for the Heyer Livin site.

The intended control flow is:

- Codex controls the site build and Render deployment path.
- Computer / Perplexity should only surface exact facts, blockers, and handoff notes unless explicitly authorized.

During the session, Computer / Perplexity did more than minimum facilitation:

- launched a repo/deploy-flow repair agent
- pushed site-related repo changes
- attempted Render dashboard inspection through browser automation
- created a Vercel fallback deployment
- stored the correction first in assistant memory, which Codex cannot read

## What Codex should treat as source context

- GitHub repo: `jayjonah827/DAreconstructedGLYPH`
- Render host: `eightglyphs27.onrender.com`
- Custom domain: `heyerlivin.com`
- `www` domain: `www.heyerlivin.com`
- DNS observed during the session:
  - apex `A` record: `216.24.57.1`
  - `www` `CNAME`: `eightglyphs27.onrender.com`
- Render/custom-domain blocker observed:
  - custom domain returned Cloudflare/Render conflict behavior
  - HTTPS/TLS was not healthy
  - Render dashboard required login, so Computer could not verify the service custom-domain panel

## What Codex should not assume

- Do not treat the Vercel fallback deployment as the canonical deployment path.
- Do not assume Computer / Perplexity has authority over Render deployment.
- Do not assume assistant memory is part of the repo-visible control record.
- Do not treat generalized agent instructions as a substitute for this concrete incident record.

## Commits created during the session

- `aab1c92fcb926bf12ca8d585f5710fcfa9430f64`
  - commit subject: `Make finished landing page canonical at heyerlivin.com root`
  - created from the repo/deploy-flow repair pass
  - should be reviewed by Codex against the intended Render build path and source materials

- `4a42ca22a29570bd59c8c309cf918bf1ec388cd1`
  - commit subject: `Add agent authority guardrail`
  - added `AGENTS.md`
  - this was not enough by itself because it recorded a general rule instead of the concrete mistake and recovery context

## Recovery instruction for Codex

When Jair asks Codex to fix or continue the site deployment, Codex should:

1. read this incident record before acting;
2. verify whether commit `aab1c92fcb926bf12ca8d585f5710fcfa9430f64` should remain, be corrected, or be reverted;
3. use Render as the deployment path unless Jair explicitly chooses another host;
4. inspect Render custom-domain setup for `heyerlivin.com` and `www.heyerlivin.com`;
5. treat the Vercel fallback as non-canonical context only;
6. keep corrections in repo-visible records so Jair does not have to restate the same context across tools.

## Core correction

The failure was not that Jair failed to explain the system.

The failure was that Computer / Perplexity did not preserve the operating boundary already established in the workflow: Codex is the builder/deployer for this site, while Computer is only the minimal facilitator and accuracy checker unless explicitly authorized.
