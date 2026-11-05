---
name: ux-review
description: Audit a web page or flow in a real browser for design-system compliance, all feedback states (loading, empty, error, not-found, unknown URL), responsiveness, keyboard and screen-reader use, i18n quality, forgiveness and vocabulary — every finding citing the rule it breaks. Use when reviewing UI work, before merging a UI PR, or when asked whether a page is "done".
---

# UX review

Read `.claude/profiles/ux.md` and the design-system document it names. The craft bar and decision
rules are in the `design-system-ui` skill's `references/craft-standards.md`. Read its "Decision
rules" before step 1, because every finding cites the rule it breaks.

1. **Run it.** Start the app with the profile's dev or preview command and drive it with the browser
   tools. With no backend, mock the API the way the profile says, or leave it failing: the error
   state is one of the things you need to see.
2. **States.** For each data-bearing surface, force each state and screenshot it:
   - loading (throttle, or delay the mock): a skeleton, and no layout jump when content lands;
   - empty (respond `[]`): an empty state with a useful action;
   - error (respond 500): a localised message with a path forward;
   - not-found (404 on a detail route): a friendly localised state with a way back;
   - unknown URL: the not-found page, never an empty shell;
   - **failure is never shown as absence**: a 500 shows an error with retry, not the "no
     results" copy.
3. **Design-system compliance.** Grep the page's styles for raw colours and off-scale media
   queries. Check that the markup composes the required primitives rather than hand-rolled
   equivalents.
4. **Responsive.** At the profile's viewports: no horizontal scroll, no truncated essentials, tap
   targets ≥ 44 px, and correct navigation behaviour at the collapse boundary.
5. **Keyboard and screen reader.** Tab through the whole page: logical order, visible focus
   everywhere, dialogs that trap and restore focus, Escape that closes, tabs on arrow keys. Run the automated
   accessibility floor and add the page to it if it is missing (`a11y-audit` covers depth).
6. **i18n.** Switch to each locale: every string translates, and nothing overflows with the longest
   locale's copy.
7. **Forgiveness and vocabulary.** No `alert()`/`confirm()` (grep the feature). Destructive actions
   offer undo, or one confirm dialog with Cancel first. The domain vocabulary is the profile's.
   Dates and numbers follow the active locale.
8. **Report** findings ordered blocker / should-fix / polish, each with the route, the evidence
   (a screenshot or a snippet) and the rule or design-system section it violates. For each blocker,
   name the failing test that should exist. Also list what is good and must not regress.
