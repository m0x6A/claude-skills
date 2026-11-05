---
feature: <issue>-<slug>
issue: <issue number>
title: <title as on the issue>
track: small
status: proposed            # proposed | approved (a person approved it) | implemented
date: YYYY-MM-DD
author: <person who owns the change>
produced_by: { model: <model id>, model_name: <model name>, tool: <client and mode>, effort: <if known> }
review: { small: pending, by: design-reviewer, date: YYYY-MM-DD }
touches: []                 # deployable names as the profile's source names them (at most two)
---

# <Title>

Issue: #<issue> · Track: small · Branch: `<per the profile, default feature/<issue>-<slug>>`

## 1. Problem

<!-- Condensed from the issue, not rewritten. Acceptance criteria verbatim. -->

**Acceptance criteria** (from the issue)

- [ ] **AC1** — ...

Prior art: <older design, ADR or closed issue on the same ground, or "none">

## 2. Spec

<!-- Same headings, numbering and columns as design.md §2, so a promotion copies it unchanged.
     Escalate or ask rather than writing a vague answer. -->

### 2.1 What the change does

- **S1** — When <actor> <does something>, <observable result>.

### 2.2 How we'll know it works

| Proves | Evidence | Kind |
|---|---|---|
| S1, AC1 | `<TestClass.Method>`: <what it asserts> | unit / integration / e2e |

### 2.3 What it must not break

| # | Must keep working | Guarded by |
|---|---|---|
| N1 | <closest neighbour: an existing caller, screen, contract or guarantee> | existing `<Test>` (opened, exercises it) / new `<Test>` |

## 3. Where it changes

- `<project>` — `<path>`: <what changes, one line>

## 4. Caveats triage

<!-- Core rows plus the profile's packs and project rows (feature-design/references/caveats.md).
     A line per row that applies; the rest on one n/a line. A full-track trigger here means escalate. -->

- <Caveat>: <answer, with what you opened>
- n/a: <Caveat>, <Caveat>, … — <shared reason>

## 5. Tasks

- [ ] **T1** — <what> · serves S1, AC1
  - Test first: `<TestClass.Method>` — fails today because <reason>
  - Files: `<path>`
- [ ] **T2** — guard for N1 · serves N1
  - Test: `<TestClass.Method>` — passes today; pins <existing behaviour>

## 6. Verification

```
<exact commands>
```

- Manual: <journey to walk and the expected result, or "none">

## 7. Decisions

<!-- Only if there was a real choice, or an override of the router. "none" otherwise. -->

- **D1** — <decision> · because <rationale> · rejected: <alternative>
- Override: <full-track trigger kept on the small track> — <the person's reason>

## Review outcome

<!-- Spec check and track check from design-reviewer, verbatim; then Accepted: lines for kept findings. -->
