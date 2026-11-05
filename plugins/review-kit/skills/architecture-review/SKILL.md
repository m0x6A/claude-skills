---
name: architecture-review
description: Run a repeatable, evidence-first architecture audit of a backend — boundaries between modules or bounded contexts, gateway rules, messaging and delivery guarantees, continuity and self-healing (migrations, retries, health checks, startup), error handling, configuration, and code organisation — producing a dated report with severities, a top-risk list and a map from finding to owning work. Use when reviewing a change that touches hosts, data access, messaging or composition, when asked whether the backend is "consistent", or to produce a periodic architecture report.
---

# Architecture review

Evidence first: every finding gets `path:line` and an excerpt you have actually read. An audit
that overstates is worse than one that misses, because people stop reading it.

Rules come from the project: `.claude/profiles/architecture.md` if present (the rule set, the
grep set, the test commands, report location), else `AGENTS.md`/`CLAUDE.md`, the ADRs and the
previous report. **Start from the previous report**, so you do not re-report what an open stream of
work already owns.

## Procedure

1. **Run the mechanical rules first.** Architecture tests (NetArchTest, ArchUnit,
   dependency-cruiser, import-linter, …) and their offender lists are the baseline. If none exist,
   say so; recommending them is a finding.
2. **Project graph.** Print the reference/import graph (`ProjectReference`s, package imports,
   workspace deps) and diff it against the boundary rules: data-access projects reference only
   their own context and shared kernels; contracts reference no data access; a host references
   another context's *contracts* only; no cycles.
3. **Gateway / edge.** No data access or business rule in the gateway (in source *or* in the
   dependency closure); every outbound call has an explicit timeout and forwards the caller's
   cancellation; faults are mapped by type, never by message text; errors are RFC 7807 problems.
4. **Messaging.** Each host configures messaging through one shared entry point with an explicit
   delivery tier (outbox/inbox/none) and a reason; consumers hold no mutable static state;
   publish-only consumers never reply; request/response consumers reply on every path; error
   queues have a depth metric and an alert.
5. **Continuity.** Migrations apply by migrate-only (never "ensure created"); database
   registration has retry on transient failure; no connection-string fallbacks; readiness checks
   cover the real dependencies (so ready ≠ live); hosts wait for their migration; backfills are
   paged and cancellable background work, not startup blocking; calls to external dependencies go
   through a resilience pipeline.
6. **Grep set.** Run it and report counts and the worst files. The defaults for .NET follow; the
   profile replaces them for other stacks:
   ```bash
   grep -rln "CancellationToken.None" src --include='*.cs' | grep -v Tests | wc -l
   grep -rn "catch (Exception)" src --include='*.cs' | grep -v Tests | wc -l
   grep -rn "DateTime.Now\b\|\.Result;\|GetAwaiter().GetResult()" src --include='*.cs' | grep -v Tests
   grep -rEn "^\s*if \(.*\)\s*$" -A1 src --include='*.cs' | grep -v "{" | head
   ```
   plus a scan for files with more than one top-level type, if the project has that rule.
7. **Configuration.** Options validated at startup; no localhost fallbacks that survive into
   production; one configuration order (files → secret store → env → local secrets).
8. **Verify before you write.** Re-check the three worst findings against runtime wiring: who
   registers the type, who publishes the message, whether the code path is reachable. Record any
   correction.
9. **Report** to the profile's location (default `doc/reviews/YYYY-MM-DD-architecture-review.md`):
   an inventory table; findings by area, with severity (**HIGH** can take production down or corrupt
   state, **MED** will bite under load or in an incident, **LOW** is hygiene); what is done
   well; the top 15 by risk; and a stream map (finding id → the issue or feature that owns it). For a PR,
   report blocker / should-fix / polish with the same evidence format and the failing test that
   should exist.
