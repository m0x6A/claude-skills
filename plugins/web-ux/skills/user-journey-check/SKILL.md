---
name: user-journey-check
description: Walk a web product's core user journeys end to end in a real browser, at phone and desktop width, and report friction — anything that breaks "one obvious next action", a dead end, lost work on refresh or session expiry, a raw loading/empty/error state, a browser dialog, a destructive action without undo. Use when validating a release, after navigation or flow changes, or when asked how the product "feels" to use.
---

# User journey check

The journeys live in `.claude/profiles/ux.md` under **Journeys**. If there are none, draft them with
the user from the router and the navigation: discover → convert, sign in → orient, each core task,
preferences, and **lost and expired** (always include it).

1. **Start the app** with the profile's command and drive it with the browser tools. Mock the API as
   the profile says when no backend runs. Walk each journey at **phone and desktop** width.
2. **Walk the journeys in order.** "Lost and expired" means: an unknown URL lands on a not-found page
   with a way home; when the session expires mid-form (clear the refresh cookie), a message explains why,
   signing in returns to the same page including its query string, and the draft is offered back.
3. **At every step, score the friction heuristics:**
   - Is the next action obvious within three seconds?
   - Is there a dead end (no back affordance, no way out of a state)?
   - Does a refresh lose work or session state unexpectedly?
   - Do loading, empty and error states look designed, or raw? Does a failed request look different from
     "nothing here"?
   - Is there a browser dialog? A destructive action with no undo?
   - On a phone: are targets reachable with a thumb, is there no horizontal scroll, and is no input
     hidden behind the keyboard?
4. **Report** an ordered friction list: route, step, severity (*blocks the journey* / *slows it* /
   *cosmetic*), what the user experiences, and the smallest fix. Name the journeys that pass cleanly too,
   because silence is not a report.
5. When a friction point maps to a missing end-to-end assertion, propose the spec addition.
