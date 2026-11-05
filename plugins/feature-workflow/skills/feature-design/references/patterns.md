# Risk areas and problematic patterns

Used by the `design-reviewer` agent and by `feature-design` at each gate. The risk map says
*where a reviewer's attention should go*; the pattern list says *what shape of mistake is
present*. Report both even when nothing is a blocker.

## Risk areas (rank the design against these; report at most five)

| Area | It is risky here when the design… | Verify before approving |
|---|---|---|
| **Data and migrations** | adds or changes columns on a hot table, backfills, changes a type, touches an index, or depends on migration order | migration name and order, rollback, backfill batch size, lock duration |
| **Identity, authorisation, privacy** | adds a privileged or cross-user route, reads another user's or tenant's data, stores PII, renders user-supplied URLs or HTML | the policy on the route, tenant resolution, audit log, erasure, CSP |
| **Cross-boundary coupling** | needs data another context owns, adds a message between contexts, duplicates data, reads another context's table | the message or gateway hop, who owns the copy, what happens when the owner changes it |
| **Concurrency and idempotency** | writes a row two actors can touch, runs on several replicas, processes a message with side effects, polls, claims work | the strategy, the token or key, the inbox, `SKIP LOCKED`, no static state |
| **External dependencies and cost** | calls an AI model, a SaaS, search or blob storage; adds per-request fan-out; stores binaries | timeout and breaker, cache and invalidation, cost per call × volume |
| **Operability** | adds a failure mode with no log, metric or alert; changes a health check; adds a background loop; changes config or secrets | dashboard panel, alert rule, runbook line, secret store |
| **User-facing irreversibility** | deletes, merges, overwrites or sends on a click; changes a default; changes navigation | confirm or undo, empty and error states, every locale |
| **Performance and scale** | lists without limits, queries in a loop, grows a payload on the bus, adds a synchronous hop to a hot path | pagination, projection, index, payload size, today's p95 |
| **Delivery and rollout** | changes shared contracts (fan-out), needs a consumer deployed before its producer, changes CI or hosting | fan-out list, deploy order, flag or additive-first sequencing |
| **Testability** | describes behaviour no test can observe (time, randomness, external calls, UI timing) | the seam, the evidence each §2.2 row names |

## Problematic patterns (name it, where it appears, why it hurts here, the alternative)

### Spec
- **Spec that describes the build, not the behaviour**: §2.1 says "add a column and a consumer" instead of what a user or caller observes. *Alternative:* "When X does Y, Z happens"; the build goes in the diagrams.
- **"Works" without evidence**: a §2.1 statement with no row in §2.2, or a row whose evidence is "manual testing". *Alternative:* a named test, or a manual check with its expected result.
- **"Nothing breaks"**: §2.3 is empty, generic, or lists only the new code. *Alternative:* name the neighbours: the existing callers, the contracts, the data and the screens next to the change, each with its guard.
- **Guard that cannot fail**: a §2.3 item guarded by a test that does not exercise it. *Alternative:* a regression test that fails if the behaviour changes.

### Architecture
- **Orchestration in the gateway**: the gateway calls two services and combines or sequences the results. *Alternative:* one command owned by whoever owns the invariant.
- **Business rule in the gateway**: a domain rule exists only in the gateway. *Alternative:* the rule in a shared policy type, applied in both places.
- **Cross-context read**: a component reads another context's table or internal type. *Alternative:* a message, or gateway-carried data.
- **Dual write without outbox**: a row is written and an event is published in two steps. *Alternative:* a transactional outbox.
- **Request/response for fire-and-forget**: a caller waits for a result nobody uses. *Alternative:* publish, answer 202, show progress from state.
- **Chatty messaging**: several round trips where one richer command would do. *Alternative:* event-carried state transfer.
- **Shared mutable static state**: static fields or in-memory caches on a component with several replicas. *Alternative:* database, cache server, distributed lock.
- **God handler or god component**: one handler or UI component grows a branch per feature. *Alternative:* one handler per command; a feature folder.
- **Leaky provider type**: an SDK type in a contract, DTO or component prop. *Alternative:* an owned type at the boundary.
- **Duplicated validation that can drift**: the same rule in two places with no shared source. *Alternative:* one definition, or a test pinning both to the same cases.

### Data
- **Editing a merged migration**, or renaming one. *Alternative:* a new migration.
- **Non-additive contract change**: a removed or renamed field, a changed meaning, renumbered enums. *Alternative:* add, default, deprecate.
- **Soft state without cleanup**: drafts, sessions, tokens or uploads with no expiry. *Alternative:* a retention rule and a sweep.
- **Stringly typed data**: units, statuses or ids as free text where a type exists. *Alternative:* the typed value, mapped for display at the edge.
- **Unbounded collection**: a list, query or include without a limit. *Alternative:* pagination or projection, and a test with N+1 rows.
- **N+1**: a query per item in a loop. *Alternative:* one query with projection; a test that counts queries.

### Concurrency and idempotency
- **Inbox assumed, not attached**: code relies on deduplication that no endpoint provides. *Alternative:* verify the wiring; add a duplicate-delivery test.
- **Read-modify-write without a token**: a row two actors can touch is saved with no version or conditional update. *Alternative:* optimistic concurrency, or a conditional `UPDATE … WHERE`.
- **Lock or transaction across a network call**: a lock or transaction is held while another service, an LLM or an HTTP endpoint is called. *Alternative:* a short claim, then the work outside the lock.
- **Request inside an outbox transaction**: a request staged until commit and so timing out. *Alternative:* a non-transactional client for requests.
- **Catch-and-continue after a database error**: a caught constraint violation inside a transaction that is already aborted (Postgres). *Alternative:* rethrow and retry, or `ON CONFLICT`.
- **Saga without a concurrency mode**: several events race for one instance. *Alternative:* a pessimistic lock or a row version, plus a concurrent-event test.
- **Work longer than the ack timeout**: the message is redelivered while it is still running. *Alternative:* a claim row with a heartbeat, or split the work.
- **Ordering assumed between messages**. *Alternative:* handle both orders, or carry a sequence number.

### Resilience
- **Retry without backoff or idempotency**. *Alternative:* an idempotency key, exponential backoff, a circuit breaker.
- **Timeout without a user-visible outcome**: the call times out and the UI keeps spinning. *Alternative:* map the timeout to an honest state.
- **Swallowed exception**: a catch that logs and continues inside a handler. *Alternative:* rethrow so the infrastructure retries and dead-letters.
- **Local time or no clock seam**. *Alternative:* UTC behind a clock abstraction.

### Frontend
- **Hand-written API types**. *Alternative:* the generated package.
- **State duplicated across stores**. *Alternative:* one owner and derived views.
- **Native `alert`/`confirm`**, or a destructive action with no undo. *Alternative:* a design-system dialog, or an undoable action.
- **Strings in one language**. *Alternative:* every locale in the same task.
- **Layout that shifts on load**. *Alternative:* a skeleton with reserved dimensions.

### Process
- **Scope creep in the plan**: tasks the design never decided. *Alternative:* the decision first, or the out-of-scope list.
- **Task that serves no spec item**: a plan task with no S or N number. *Alternative:* tie it to the spec, or cut it.
- **Caveat answered from memory**: an "n/a" with no file cited. *Alternative:* open the file.
