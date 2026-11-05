# UX profile — <app>

Read by every web-ux skill and the ux-critic agent. Commit as `.claude/profiles/ux.md`.

## App
- Directory: `<path to web app>`
- Dev: `<yarn dev>` → `<http://localhost:3000>` · Production preview: `<yarn build && yarn preview --port 4173>`
- API mocking when no backend runs: `<e.g. Playwright route fixtures in e2e/fixtures/api.ts, MSW handlers>`
- Signed-in surfaces: `<how to get a session: mock, seed user, test login>`

## Design system
- Source of truth: `<doc/DESIGN_SYSTEM.md>`
- Tokens: `<src/styles/_variables.scss | tokens.css | tailwind.config>` · raw colours forbidden outside token definitions: yes/no
- Breakpoints: `<480/768/996/1200>` from `<file>` · never hard-coded pixels
- Required primitives: `<Button, TextInput, Modal, Toast, Skeleton, EmptyState, PageHeader, Card, ConfirmDialog>`
- Guards: `<tests that fail on token or breakpoint regressions>`

## Quality gates
- Lint/test/build: `<yarn lint:ci && yarn test:ci && yarn build>`
- E2E: `<yarn test:e2e>` · Accessibility floor: `<npx playwright test e2e/a11y.spec.ts>` (zero serious/critical axe violations)
- Unit test style: `<Vitest + Testing Library, colocated __tests__/>`

## Locales
- `<en, sv>` · files: `<src/i18n/locales/*/common.json>` · switch: `<localStorage.i18nextLng = 'sv'>`
- Date/number/sort helpers: `<formatDate, Intl.Collator(language)>`

## Viewports
- Phone `<390>` · tablet `<768>` · desktop `<1280>` · nav collapse at `<996>`

## Vocabulary
- `<domain terms the UI must use, and the ones it must not>`

## Journeys (user-journey-check)
1. **<name>**: `<route>` → `<route>` → … (what "done" looks like)
2. …
