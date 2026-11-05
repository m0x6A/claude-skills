# web-ux

Build and judge web UI against an explicit craft bar, in a real browser.

- **design-system-ui**: tokens only, the breakpoint scale, required primitives, all four data states
  (loading, empty, error, not-found), every string localised, test first. Includes
  `references/craft-standards.md` (the "never ship" list and the "instead of X, do Y" decision rules).
- **ux-review**: forces every state, checks design-system compliance, viewports, keyboard, i18n,
  forgiveness and vocabulary; each finding cites the rule it breaks.
- **a11y-audit**: WCAG 2.2 AA: the axe floor, then the manual checklist, with fixes written test first.
- **user-journey-check**: walks the core journeys (including "lost and expired") at phone and desktop
  width and reports friction by severity.
- **ux-critic** agent: runs all of the above and returns `ships | ships after should-fixes | not done`.

## Setup

On first use, create `.claude/profiles/ux.md` from
`skills/design-system-ui/references/ux-profile-template.md`: app directory, commands, API
mocking, design-system doc, primitives, locales, viewports, vocabulary, journeys. A browser tool
(the Claude desktop built-in browser, Claude in Chrome or Playwright) is needed for the
in-browser steps.
