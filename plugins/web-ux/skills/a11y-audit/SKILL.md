---
name: a11y-audit
description: Run a WCAG 2.2 AA accessibility audit of a web page or flow — the automated axe floor first, then the manual pass that catches the other ~60% (keyboard-only walk, focus management in dialogs, name-role-value of custom widgets, contrast of new colour pairings, 200% zoom and reflow, reduced motion, live regions, target size) — and fix defects test first. Use when checking accessibility compliance, fixing a11y defects, or before shipping UI that changes interaction patterns.
---

# Accessibility audit

Read `.claude/profiles/ux.md` for the app's commands, primitives and locales. Checklist:
`references/wcag-checklist.md`. Check each item at phone and desktop width.

1. **Automated floor first.** Run the profile's axe scan (for example a Playwright spec with
   `@axe-core/playwright`). Zero serious or critical violations is the merge bar. Add the page
   under audit to the scan if it is not covered. If the project has no scan, adding one is the first
   recommendation.
2. **Manual pass.** Axe catches about 40%. Walk `references/wcag-checklist.md` in the browser:
   keyboard only; focus into, within and out of dialogs and sheets; the accessible name, role and
   value of every custom widget; contrast of any **new** token pairing; 200% zoom and 320 px reflow;
   `prefers-reduced-motion`; announcements for transient feedback.
3. **Project hot spots.** Dialogs use the modal primitive or a focus-trap hook (trap, Escape,
   restore), never a bare overlay. Tab UIs use `tablist` with roving tabindex and arrow keys.
   Transient feedback goes through the toast primitive (`role="status"`/`"alert"`, dismissible,
   pause on hover). The global `:focus-visible` outline may be strengthened by components and never
   removed. Contrast is checked against the documented token pairings; never lighten text tokens.
4. **Fix test first**: a failing interaction test or axe assertion, then the fix.
5. **Report** as WCAG criterion → element or route → impact → fix. After fixes, re-run step 1 and
   confirm it is green. Note anything that needs a screen-reader spot check (VoiceOver, NVDA) and the result.
