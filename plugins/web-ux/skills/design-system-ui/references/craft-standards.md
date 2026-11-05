# Craft standards

Judge every surface the way a demanding product designer would. These standards are what the
`ux-review` skill and the `ux-critic` agent cite.

## Philosophy

- **Clarity over decoration.** Type, spacing and colour exist to communicate. If an element does not
  help the user decide or act, remove it.
- **One dominant action per surface.** Users should never have to scan for what to do next. Demote or
  remove competing emphasis.
- **Deference.** The interface serves the content. Chrome stays quiet.
- **Depth with restraint.** Elevation signals hierarchy, not decoration: one elevation change per
  interaction.
- **Perceived performance is design.** Skeletons shaped like the incoming content, optimistic
  affordances, motion of 100–300 ms with ease-out.
- **Honesty.** Absence and failure are different facts, so never show one as the other.
- **Forgiveness.** Prefer undo to confirmation, and never lose what the user typed.

## Never ship

- Two competing accent hues on one surface.
- Text under 4.5:1 contrast on its surface (3:1 for large text and UI graphics).
- A clickable `div`/`li`/icon. Interactive means `<button>`, `<a>` or `<input>`.
- A dialog that loses keyboard focus, or a toast that cannot be dismissed.
- Layout jumps when data lands.
- Truncated or overflowing text at phone width, or tap targets under 44×44 px.
- An empty screen with no explanation and no next action.
- Motion that ignores `prefers-reduced-motion`.
- A string in the wrong language for the active locale.

## Decision rules

| Instead of | Do | Why |
|---|---|---|
| Showing a failed request with the empty-state copy ("Nothing matched") | Branch on error before results; show an error with retry | Honesty |
| `alert()` / `window.confirm()` | A toast for outcomes, inline field errors for validation, a confirm dialog (Cancel first) only for irreversible actions | Browser dialogs cannot be styled, localised or focus-managed |
| A confirm dialog before every delete | Do the delete, show an Undo toast for about 6 s, and commit after | Undo keeps the flow moving; dialogs train click-through |
| Discarding work on a scrim click, a navigation or a session expiry | An unsaved-changes guard, a draft stash, and return-to with the query string | Never lose what the user typed |
| A router with no catch-all | A not-found page with one link home | No dead ends |
| A page reachable only by URL | Put it in navigation, or remove it | Every destination is discoverable |
| Two words for one domain concept | The profile's vocabulary | One vocabulary |
| A primary button above the inputs it depends on | Inputs first, then one primary action last | Reading order is input → action |
| Several different "back" mechanisms | The page header's back affordance | Consistency |
| Server prose (`error.message`) in the UI | Map error codes to translation keys | No untranslated text |
| `toLocaleDateString('en-US')`, `[A-Z]` grouping | Locale-aware formatting and `Intl.Collator(language)` | Platform respect (Å, Ä, Ö, ß exist) |
| A hand-rolled `<div role="dialog">` | The modal primitive | Focus trap, Escape, restore, scrim and name for free |
| A `transition` without a reduced-motion override | The motion helper | Accessibility baseline |
| A hand-written API type | The generated contracts package | Contracts never drift |

## The test

Before calling UI work done, walk it at phone and desktop width, keyboard-only, in every locale,
on a throttled network, and ask:

1. Would this ship on the best product site you know?
2. Is there exactly one obvious next action?
3. Do loading, empty, error and success all feel designed?
4. Could you remove anything without losing meaning?

If any answer is no, it is not done.
