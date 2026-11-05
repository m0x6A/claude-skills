# Diagram style

Every diagram in a design is a *sheet* in a drawing set: one question answered, in one visual
language, so a reader who has learned it once can read every design. The same Mermaid source renders
on GitHub (light classDef values below) and on the render page (`render.html` swaps them for its
light or dark palette and applies the typeface), so write it once, here, by these rules.

## The rules that make a diagram clear

1. **One question per sheet.** The system map answers *where*, the sequence *in what order*, the
   control flow *what can happen*, the data flow *what moves where*. If a sheet answers two, split it.
2. **At most about twelve nodes.** Past that, group into a `subgraph` per bounded context, or split
   the sheet. A pipeline longer than eight steps runs `TB`, not `LR`.
3. **Colour means change, not decoration.** Only three things get colour: what this feature
   *changes* (`affected`), what it *adds* (`new`) and *failure outcomes* (`err`). Everything else is
   `quiet`. A sheet where everything is blue says nothing.
4. **Labels on one line**, parts separated by ` · ` (many renderers drop `<br/>`). Name the real
   thing: `POST /orders/{id}/cancel`, `OrderCancelled`, `orders.status`, not "request" or "event".
5. **Every edge that carries data is labelled** with the contract it carries.

## Shapes

| Thing | Mermaid | Example |
|---|---|---|
| Person or entry point | `([ ])` | `User([customer])` |
| Deployable (service, app, gateway, job) | `[ ]` | `Orders[Orders.Api]` |
| Store (database, cache, bucket) | `[( )]` | `OrdersDb[(orders db)]` |
| Broker, queue, topic | `{{ }}` | `Bus{{rabbitmq}}` |
| Decision | `{ }` | `Auth{caller owns order?}` |
| Outcome (end of a branch) | `([ ])` + `:::ok` or `:::err` | `E409([409 already shipped]):::err` |
| Outside our system | `[ ]` + `:::ext` | `Psp[payment provider]:::ext` |

## Edges

| Meaning | Mermaid |
|---|---|
| synchronous call (HTTP, request/response) | `A -- GetOrder --> B` |
| asynchronous message or event | `A -. OrderCancelled .-> B` |
| new in this feature (either kind) | `A == RefundRequested ==> B` |

## The class block

Paste this at the top of every `flowchart` (and use `class X new` lines in a `stateDiagram-v2`).
Keep the names; `render.html` recognises them and re-colours them for dark mode.

```
classDef affected fill:#E7EDFB,stroke:#2F5BD3,stroke-width:2px,color:#13244F
classDef new fill:#DFF2EA,stroke:#0F8A6A,stroke-width:2px,color:#0A3A2C
classDef quiet fill:#FFFFFF,stroke:#A7B0BC,stroke-width:1px,color:#3F4855
classDef ext fill:#F2F4F7,stroke:#A7B0BC,stroke-width:1px,stroke-dasharray:4 3,color:#3F4855
classDef ok fill:#FFFFFF,stroke:#1B2330,stroke-width:1.5px,color:#1B2330
classDef err fill:#FBE8EC,stroke:#C2334D,stroke-width:1.5px,color:#5A1424
```

Bounded contexts are subgraphs with a short title: `subgraph orders [Orders]` … `end`. Leave their
styling to the renderer.

## Sequence diagrams

- Start with `autonumber`, so the text and review can cite steps ("step 4 times out").
- Group participants by context with `box`, using these tints (they read in light and dark):
  `box rgba(47,91,211,0.07) Orders` for a context this feature changes, `box rgba(120,130,145,0.07) Billing`
  for the others.
- Wrap the steps this feature adds in `rect rgba(15,138,106,0.10)` … `end`.
- `->>` is a call, `-->>` its reply, `-)` an async message. Put the timeout in the label
  (`Cancel · timeout 10 s`).
- Show every outcome with `alt` / `else` (`alt shipped` → `409`), and state idempotency or retries
  in a `Note right of Handler: dedupe on OrderId`.
- `activate` / `deactivate` a participant only when the reader needs to see who is busy while waiting.

## Data model and states

- `erDiagram`: only the tables and columns this feature adds or changes, plus the keys they hang
  off. Mark each new column with the comment `"new"`, a changed one with `"changed"`.
- `stateDiagram-v2`: use the class block (`classDef new …`, then `class Refunding new`) for new
  states; label each transition with the event or command that causes it.

## Before you publish

Read each sheet as the approver will: can they say in one sentence what it shows and what changed?
If not, cut nodes, not words.
