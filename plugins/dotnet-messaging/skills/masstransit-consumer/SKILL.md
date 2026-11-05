---
name: masstransit-consumer
description: Add or fix a MassTransit consumer and its host wiring in .NET — choose the delivery guarantee (transactional outbox and inbox vs idempotent-by-key), design additive message contracts, keep consumers stateless across replicas, respond on every path for request/response but never for published messages, rethrow instead of swallowing, forward cancellation, register dependency health checks, make failures debuggable at 3 am (error-queue alert, structured logs with message id and business key, an unbroken trace), and prove idempotency with a redelivery test. Use when creating a consumer or message contract, choosing outbox settings, or debugging duplicate, lost, stuck or dead-lettered messages.
---

# MassTransit consumer

Project facts (the shared registration helper, which hosts run which tier, contract project
layout, test conventions) belong in the project's guidance file. Read it first. If every host
configures MassTransit inline, recommend **one shared registration extension** that takes the
DbContext and the tier explicitly. Inline `AddMassTransit` per host is how hosts drift apart.

## 1. Pick the delivery guarantee, and write why next to the registration

| Tier | When | Wiring |
|---|---|---|
| **Transactional outbox and inbox** | the consumer writes to its database **and** publishes or sends, and a lost or duplicated message is unacceptable | `AddEntityFrameworkOutbox<TDbContext>(o => { o.UsePostgres(); o.UseBusOutbox(); })` and **`UseEntityFrameworkOutbox<TDbContext>(context)` on the receive endpoint** (for example through `AddConfigureEndpointsCallback`) |
| **Idempotent by key, no outbox** | writes are naturally idempotent (upsert by key, conditional update) and downstream can recover from a missed event | plain endpoint; a redelivery test proves the idempotency |
| **None** | pure queries with no side effects | plain endpoint |

Registering the outbox is not enough: deduplication and the atomic publish happen only on
endpoints that have the outbox *attached*. Check the endpoint. The outbox DbContext must be the
scoped one your repositories use, or the writes and the outbox commit separately.

## 2. Contracts

- `sealed record`s in a contracts project that references no data access. Serialisation needs a
  usable constructor path, so test it.
- **Additive only**: add fields with defaults; never remove, rename or change meaning; enums only grow.
- Events carry the state consumers need (event-carried state transfer), not just ids that force a
  call back.

## 3. Stateless consumers

The only `static` allowed is `static readonly` constants. Cooldowns, locks and "last run" belong in a
database row claimed by a conditional update, a distributed/advisory lock, or Redis, never in a field:
replicas and restarts defeat it. A test that resets a static by reflection is a smell, not a fixture.

## 4. Respond or publish, never both

- A **request/response** consumer (an `IRequestClient<T>` on the other side) calls
  `context.RespondAsync` on **every** exit path, including skip and reject, with a typed result.
  A path that never responds becomes a caller timeout.
- A consumer of a **published** message never calls `RespondAsync`. With no `ResponseAddress`,
  MassTransit publishes the response instead, so every reply goes out to all subscribers.

## 5. Failures

- Rethrow, so retry and dead-lettering work. Log-and-swallow hides the failure and commits the inbox
  as if the message succeeded.
- Exceptions that must never be retried (validation, a permanently failed external call) go on the
  retry policy's `Ignore<T>()` list in the shared configuration, not in a try/catch.
- Read-modify-write on a row two actors can touch: a conditional `ExecuteUpdateAsync` with a
  `WHERE` on the expected state, or an optimistic concurrency token (`xmin` on PostgreSQL).
- In PostgreSQL, a caught unique-violation inside the consume transaction aborts that
  transaction. Rethrow and let the retry re-check, or use `ON CONFLICT`.
- Long work: if a consumer can outlive the broker's ack timeout (RabbitMQ `consumer_timeout`,
  30 minutes by default), it is redelivered while it is still running. Split it, or use a claim row
  with a heartbeat.
- Never call a request client from inside an outbox transaction; the request is staged until commit
  and times out. Use a non-transactional client for requests.

## 6. Cancellation

Pass `context.CancellationToken` into every repository, HTTP and publish call.

## 7. Host wiring

- Health checks for the database, the broker and any other dependency, so readiness reflects
  dependencies (ready ≠ live).
- Options validated on start: `ValidateDataAnnotations().ValidateOnStart()`.
- External calls (AI, HTTP) through a resilience pipeline (timeout, retry with backoff, circuit breaker).

## 8. The 3 am question

Before the tests, ask: *if I were on call at 3 am and this consumer was failing, what observability
would I need to solve it?* With only dashboards, logs and traces, on-call must be able to tell:

- **that it is failing**: the error (`_error`) queue for this endpoint has a depth metric and an
  alert, and retries are visible (a retry count or a log per attempt), not silent;
- **which message and which record**: failures log at Warning/Error with the message id,
  correlation id and the business key (order id, user id) as structured fields; the fault that lands
  in the error queue carries the exception, so the reason travels with the message;
- **where in the flow**: the trace continues from the publisher or gateway through the consumer
  (MassTransit's OpenTelemetry source registered), and calls to the database and external services
  appear as child spans;
- **what to do first**: a duplicate dropped by the inbox or by idempotency logs once at Information
  ("already processed <key>"), so a "missing" side effect can be told apart from a lost message;
  the runbook line says whether moving the error queue back is safe (it is, if the consumer is
  idempotent).

A missing signal from this list is part of the change, not a follow-up.

## 9. Tests (write the failing test first)

- Use the MassTransit test harness (`AddMassTransitTestHarness`), or substitute `ConsumeContext<T>`
  (`Message`, `CancellationToken`, `Headers`).
- Assert publishes (`harness.Published.Any<TEvent>()`), and assert `RespondAsync` on every path for
  request/response consumers.
- **One failure-signal test**: on the failure path, assert the log carries the message id and business
  key (log capture or a fake logger), so the 3 am signal cannot silently disappear.
- **One redelivery test**: the same message twice, then assert the outcome happened once. For the
  outbox tier, run it with the production endpoint configuration, so that the test proves the inbox
  is attached.

## 10. Ship

Bump the version of every deployable that compiles a changed contracts project. If the DbContext
changed, follow `ef-core-migration`.

Licensing note: check the MassTransit version's licence terms before you upgrade across a major version.
