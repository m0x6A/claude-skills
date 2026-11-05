---
name: masstransit-consumer
description: Add or fix a MassTransit consumer and its host wiring in .NET — choose the delivery guarantee (transactional outbox and inbox vs idempotent-by-key), design additive message contracts, keep consumers stateless across replicas, respond on every path for request/response but never for published messages, rethrow instead of swallowing, forward cancellation, register dependency health checks, and prove idempotency with a redelivery test. Use when creating a consumer or message contract, choosing outbox settings, or debugging duplicate, lost, stuck or dead-lettered messages.
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

## 8. Tests (write the failing test first)

- Use the MassTransit test harness (`AddMassTransitTestHarness`), or substitute `ConsumeContext<T>`
  (`Message`, `CancellationToken`, `Headers`).
- Assert publishes (`harness.Published.Any<TEvent>()`), and assert `RespondAsync` on every path for
  request/response consumers.
- **One redelivery test**: the same message twice, then assert the outcome happened once. For the
  outbox tier, run it with the production endpoint configuration, so that the test proves the inbox
  is attached.

## 9. Ship

Bump the version of every deployable that compiles a changed contracts project. If the DbContext
changed, follow `ef-core-migration`.

Licensing note: check the MassTransit version's licence terms before you upgrade across a major version.
