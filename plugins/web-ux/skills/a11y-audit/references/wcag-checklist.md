# WCAG 2.2 AA checklist

Check each item at phone (≈390 px) and desktop (≈1280 px) width.

## Keyboard (2.1.x, 2.4.x)

- [ ] Every interactive element is reachable with Tab in a logical order; nothing needs a mouse.
- [ ] No keyboard trap except intentional dialog traps, and Escape always exits them.
- [ ] A visible focus indicator on every focusable element; the focused element is never fully obscured (2.4.11).
- [ ] Dialogs and sheets: focus moves in on open, cycles within, and returns to the invoker on close.
- [ ] Tabs: arrow keys move the selection; only the active tab is in the Tab order.
- [ ] No positive `tabindex`; a skip link past repeated blocks where they exist.

## Semantics and names (1.3.1, 4.1.2)

- [ ] Interactive means a native `<button>`/`<a>`/`<input>`; no clickable `div`/`li`/icon.
- [ ] Every control has an accessible name (visible label, `aria-label` or `aria-labelledby`) in the **current** locale.
- [ ] One `h1` per page; heading levels don't skip.
- [ ] Landmarks: header, nav, main and footer present and unique; several navs each have a name.
- [ ] Form fields: a programmatic label, `aria-invalid` plus error text announced (`role="alert"` or `aria-describedby`), and `autocomplete` where relevant.

## Perceivable (1.4.x)

- [ ] Text contrast ≥ 4.5:1 (≥ 3:1 for large text and UI graphics) on the documented pairing. Verify with the scan, not by eye.
- [ ] Nothing is conveyed by colour alone; status also has an icon or text.
- [ ] Meaningful images have alt text; decorative icons are `aria-hidden`.
- [ ] Usable at 200% zoom, and at 320 px reflow with no horizontal scroll.

## Announcements and motion (4.1.3, 2.3.3)

- [ ] Transient feedback is announced through a live region (`role="status"` polite, `role="alert"` assertive).
- [ ] Loading surfaces expose `aria-busy` and have an accessible name.
- [ ] Route changes move focus and update the title sensibly; `document.title` changes.
- [ ] Decorative animation is disabled under `prefers-reduced-motion: reduce`.

## Pointer and touch (2.5.x)

- [ ] Targets are at least 24×24 px (2.5.8). 44×44 px is the recommended house bar.
- [ ] No functionality requires dragging or multi-point gestures without an alternative (2.5.7).

## Authentication and help (3.3.x, 3.2.6)

- [ ] No cognitive test to log in; paste and password managers work (3.3.8).
- [ ] Information already entered is not asked for again in the same flow (3.3.7).
- [ ] Help mechanisms sit in a consistent place across pages (3.2.6).

## Process

- The automated floor (axe: zero serious or critical violations).
- A screen-reader spot check of the changed flow.
- Every locale: names and announcements translate, and long copy doesn't overflow controls.
