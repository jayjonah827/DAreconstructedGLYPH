# Agent Authority Guardrail

Codex controls the Heyer Livin site build and Render deployment flow.

Computer / Perplexity is not the builder, generator, or deployment controller for this site unless Jair explicitly authorizes that role for a specific task.

Computer / Perplexity should only provide minimum facilitation:

- surface exact repo, domain, DNS, Render, and deployment facts
- open or point to required account screens when asked
- check accuracy against source records rather than reinterpret the framework
- record blockers, handoff notes, and unresolved states
- avoid rebuilding, replacing deployment paths, creating fallback deployments, pushing repo changes, or acting as the controlling deployment agent unless Jair explicitly asks

If Computer / Perplexity makes an error, the correction must be recorded in this repo-visible guardrail or another source-of-truth file that Codex can access, not only in assistant memory.
