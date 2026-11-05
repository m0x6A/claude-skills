---
name: design-system-ui
description: Build or modify web UI through the project's design system — semantic tokens only, the breakpoint scale, required primitives instead of hand-rolled ones, every data surface shipping loading, empty, error and not-found states, every string localised, test first — and to an explicit craft bar (one obvious action, honest failure, forgiveness over confirmation). Use when creating or styling any component, page or state in a web app.
---

# Design-system UI

Read `.claude/profiles/ux.md` (create it from `references/ux-profile-template.md` if missing), then
the design-system document it names. Read it **before** writing UI code. Craft bar and decision rules:
`references/craft-standards.md`.

1. **Extend, never fork.** If the change needs something the system cannot express, extend the
   system (a token or primitive, plus the doc update, in the same change). Never add a local
   one-off.
2. **Colours only from semantic tokens.** No raw hex/rgb, and no palette steps outside token
   definitions. If the project has a guard test for this, it must stay green.
3. **Breakpoints from the scale**, via the project's mixins or constants. Never hard-code pixel widths.
4. **Compose the required primitives**: button, input, modal/dialog, toast, skeleton, empty
   state, page header, card. A bespoke dialog or banner is a defect, because the primitive brings focus
   trapping, live regions and consistency for free.
5. **Every data-bearing surface ships all states**: a skeleton shaped like the content while
   loading (no layout jump), an empty state with a next action, an error with a localised message and a path
   forward, and not-found. **Failure is never shown as absence**: branch on error before "no results".
6. **Every string through the translation function**, with keys added to every locale in the
   same change. Dates, numbers and sorting use the locale helpers, never a literal `'en-US'`.
7. **Test first.** A failing component or interaction test, then the code.
8. **Gate before commit**: the profile's lint, test, build and e2e commands.
9. **UI changes include desktop and phone screenshots.**
