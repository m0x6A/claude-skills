---
name: bff-gateway-endpoint
description: Add or change an endpoint on a .NET backend-for-frontend (BFF) or API gateway that forwards to services over MassTransit request clients — the thin-gateway rule (no database, no business logic), an explicit timeout per policy, cancellation forwarded, faults mapped by type to 504/404/409/403/503/429/500 as RFC 7807 problems, sealed DTO records, authorisation and OpenAPI metadata on the route, and tests for every mapped outcome. Use when touching gateway or BFF endpoints or when the frontend needs a new route.
---

# BFF gateway endpoint

The gateway is thin: HTTP in, a message out, HTTP back. It never opens a database, never holds a
business rule, and never orchestrates two services (that belongs to whichever service owns the
invariant). Project specifics, such as the broker base class, the timeout policy table and the
authorisation policies, belong in the project's guidance file. Read it first.

1. **Shape.** One folder per operation (`<Area>/<Operation>/`), one type per file: the handler
   (broker), the request as a `sealed record`, the response as a `sealed record`. If the frontend
   consumes generated types, mark the records the way the generator expects.
2. **Timeout.** Every `GetResponse` passes an explicit `RequestTimeout` from a policy table, for
   example *query* 10 s, *command* 30 s, *long AI* 120 s. Anything slower must publish and let the
   client poll a status resource (202 + `Location`). A shared base class that enforces the table
   is better than literals.
3. **Cancellation.** Pass the request's `CancellationToken` into `GetResponse`/`Publish`.
   `CancellationToken.None` is a review blocker.
4. **Fault mapping.** `RequestTimeoutException` → 504. A `RequestFaultException` is classified by
   the fault's exception type (`ex.Fault?.Exceptions` → `ExceptionType`), wrapped once in a helper
   such as `IsFaultOf<T>()`: not found → 404, concurrency conflict → 409, unauthorised → 403,
   dependency unavailable → 503, rate limited → 429, anything else → 500. **Never inspect
   `ex.Message`.** Errors are `Results.Problem(...)` (RFC 7807); successes are the DTO.
   Alternatively, return typed result unions from the consumer (`GetResponse<TOk, TNotFound>`)
   so expected outcomes are not faults at all.
5. **Logging and the 3 am question.** Ask: *if I were on call at 3 am and this endpoint failed, what
   would I need to solve it?* `ILogger<THandler>`; log faults at Warning with the correlation id, the
   target request type, the elapsed time and the mapped status, as structured fields, not
   interpolated text. Return the trace id in the problem details (`traceId`) so a user report leads to
   the trace. Keep the trace flowing through the request client (MassTransit's OpenTelemetry source
   on both sides), so one trace shows gateway → broker → consumer. A timeout names the service that
   did not answer. A `catch (Exception) { return 500; }` without a log is a blocker.
6. **Contracts.** After changing a request or response type, regenerate the frontend's types with
   the project's generator. Never hand-write them.
7. **Route.** `MapGet`/`MapPost` in the area's endpoint extension, `.RequireAuthorization(<policy>)`
   matching the project's policies, the target id taken from the route (never trusted from the
   body), and OpenAPI metadata (`.Produces<TDto>()`, `.ProducesProblem(...)`).
8. **Tests** (failing first): substitute `IRequestClient<T>`. Assert the status for the happy path,
   for a timeout and for each mapped fault, and that the timeout and fault paths log with the
   correlation id (a fake logger or log capture). Assert the token is forwarded
   (`Arg.Is<CancellationToken>(t => t == token)`). Add an architecture test that the gateway assembly
   references no data-access package.
9. **Ship**: format, test, and bump the gateway's version (and the frontend's if its types changed).
