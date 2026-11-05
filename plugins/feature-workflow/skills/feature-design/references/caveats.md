# Caveats checklist for a system design

Answer every row of **core** plus each pack the project profile enables, plus the profile's
own rows. Open the thing in "Look at" before answering. "n/a" needs a reason. Any existing
behaviour a caveat shows the change could break also goes into the design's §2.3 *What it must
not break*, with its guard.

## Core (always)

| Caveat | Question to answer | Look at |
|---|---|---|
| Boundaries | Does the feature need data or behaviour another module, service or team owns? How does it get there? Does anything reach into another owner's tables or internals? | the architecture doc, the owning module's public API |
| Idempotency | What happens when each new or changed handler runs twice, twice at once, or fails halfway? What dedupes a *new* request with the same intent? Which side effects leave the database, and what makes them safe to repeat? | existing handlers in the same component, the dedupe/inbox mechanism and where it is attached |
| Concurrency | Which rows or records can two actors write, and what is the strategy (token, conditional update, lock, unique index)? What runs on more than one replica? Is a lock or transaction held across a network call? Which isolation level applies? | entity mappings, replica counts, lock providers |
| Schema change and rollback | Which migration, is it additive, what is the rollback, is there a backfill (batched, resumable)? | the migrations folder and its conventions |
| Contract compatibility | Does any existing API, message or event gain a required field, lose a field, or change meaning? Who compiles or consumes it? | the contracts, generated clients, the fan-out tool |
| Authorisation and tenancy | Which policy guards each new entry point? How is the tenant/owner resolved? Can a user reach another tenant's data? | the auth policies, the tenant resolution code |
| Observability (the 3 am question) | If you were on call at 3 am and this broke, what would you need to solve it? For each new failure mode: what alerts or shows it, which log line (with which ids), metric or trace span localises it, which dashboard or alert changes. The answers become §2.4 rows. | the telemetry setup (correlation id, span names, log fields), dashboards/alerts as code |
| Cost | Storage, external calls (AI, SaaS), egress, new cloud resources, per-request fan-out? | the cost dashboard or budget notes |
| Testability | Can every statement in §2.1 and every guard in §2.3 be observed by a test or a check? Which seam (clock, provider, fake)? | the test projects, existing fakes |

## Pack: messaging (broker, consumers, sagas, outbox)

| Caveat | Question to answer | Look at |
|---|---|---|
| Delivery tier | Must the side effects survive a broker outage? Does the host run an outbox, an inbox, neither? Is it attached to *this* endpoint? | the host's messaging registration |
| Respond or publish | Request/response handlers reply on every path, including skip and reject; handlers of published messages never reply | the handler and its caller |
| Ack timeout | Can a handler run longer than the broker's ack or visibility timeout and be redelivered while it is still running? | broker config, the slowest handler today |
| Saga concurrency | Does each saga set a concurrency mode (pessimistic lock or row version)? | the saga registration |
| Ordering | Is any order between messages assumed? | the event flow in the data-flow diagram |

## Pack: gateway (BFF / API gateway)

| Caveat | Question to answer | Look at |
|---|---|---|
| Thin gateway | Does any new gateway code read a database, hold a business rule, or orchestrate two services? | gateway handlers |
| Timeouts and cancellation | An explicit timeout per call, the caller's cancellation token forwarded, each fault mapped to a status (504, 404, 409, 403, 503, 429, 500) | the broker/handler base class |
| Error shape | Errors as RFC 7807 problems; nothing parses exception messages | the error mapping |

## Pack: web-frontend

| Caveat | Question to answer | Look at |
|---|---|---|
| i18n | Every new string in every locale? Dates, numbers and sorting through locale helpers? | the locale files |
| CSP and hosting | Does the feature load an image, script, font, frame or connect to a host not already allowed? | the CSP / hosting config |
| States | Loading, empty, error, not-found designed for each new surface; failure never shown as absence | the design system doc |
| Generated types | The frontend imports API types from the generated package, not hand-written copies | the contracts package |

## Pack: data

| Caveat | Question to answer | Look at |
|---|---|---|
| Hot tables | Does the migration lock a large or hot table? How long? | table sizes, the database's locking behaviour for this DDL |
| Unbounded reads | Is every new list paginated or limited? Is every new predicate indexed? | the query and the indexes |
| Retention | Do drafts, sessions, tokens or uploads have an expiry and a purge? Does erasure (GDPR) reach the new data? | the retention/erasure code |

## Pack: ai (LLM and model calls)

| Caveat | Question to answer | Look at |
|---|---|---|
| Resilience | Timeout, retry with backoff, circuit breaker, and an honest user-visible outcome when the model fails | the resilience pipeline |
| Cost and quotas | Calls × expected volume × price; rate-limit behaviour; caching | the model deployment and its quota |
| Model lifecycle | Retirement date of the model or version; what the switch costs | the provider's model lifecycle page |
| Data handling | What user data is sent to the model, and is that covered by the privacy policy? | the prompt construction, the policy |
