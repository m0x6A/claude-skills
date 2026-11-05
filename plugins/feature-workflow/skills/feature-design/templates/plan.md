---
feature: <issue>-<slug>
issue: <issue number>
title: <feature title>
status: proposed            # proposed | approved (a person approved it) | implemented
date: YYYY-MM-DD
author: <person>
design: design.md
produced_by: { model: <model id>, model_name: <model name>, tool: <client and mode>, effort: <if known> }
review: { stage2: pending, by: design-reviewer, date: YYYY-MM-DD }
touches: []
---

# <Feature title> — implementation plan

Issue: #<issue> · Design: [design.md](design.md) · Branch: `feature/<issue>-<slug>`

Every task names the failing test written first, the files it touches, the spec items it serves
(S/N numbers from design §2), and the skill to use. Tick tasks as they land.

## 0. Spec at a glance

<!-- Copied from design §2 in one line each, so the plan can be read on its own. -->

- **Does:** S1 …; S2 …
- **We'll know it works when:** <the evidence from design §2.2, one line per item>
- **Must not break:** N1 …; N2 …

## 1. <Project, e.g. contracts and handler>

- [ ] 1.1 **Test first:** `<TestClass.Method>` fails because ... — serves: S1 — files: `src/...` — skill: `...`
- [ ] 1.2 ...

## 2. <Project, e.g. gateway>

- [ ] 2.1 **Test first:** ... — serves: S2
- [ ] 2.2 Regenerate generated clients (if the stack has them)

## 3. <Project, e.g. web app>

- [ ] 3.1 **Test first:** ... — serves: ...
- [ ] 3.2 Strings in every supported locale

## 4. Specs, decisions and indexes

- [ ] 4.1 Update the living spec(s), in place
- [ ] 4.2 ADR(s): ...  or "none"
- [ ] 4.3 Version bumps the stack requires: <list>
- [ ] 4.4 Row in the central feature index
- [ ] 4.5 Per-project history rows: <list>

## 5. Verification: proving the spec

<!-- Every row of design §2.2 and §2.3 appears here with the task that produces its evidence.
     The PR is not ready until every box is ticked. -->

**It works** (design §2.2)

| Spec item | Evidence | Task | Done |
|---|---|---|---|
| S1, AC1 | `<TestClass.Method>` | 1.1 | [ ] |
| S2 | <production signal and expected value>, checked after deploy | — | [ ] |

**Nothing it must not break is broken** (design §2.3)

| # | Guard | Task | Done |
|---|---|---|---|
| N1 | existing `<Test>` still green / new regression `<Test>` | 1.2 | [ ] |
| N2 | <check> | | [ ] |

- [ ] Full test commands: ...
- [ ] Journey: ...
- [ ] Screenshots at desktop and phone widths for UI changes
- [ ] Both documents `status: implemented` after merge; issue closed by the PR

## 6. Review outcome

_Not yet reviewed._
