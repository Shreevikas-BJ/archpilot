# Responsibility and durability review

ArchPilot now evaluates a technology's assigned responsibility and failure behavior,
as well as whether it is an appropriate product. This applies to newly generated
designs and revisions. Existing saved designs are not retroactively approved by the
new review.

## Six logical planes

| Plane | Responsibility |
| --- | --- |
| Durable data | Authoritative committed records; ScyllaDB/Cassandra-style hot message history for messaging designs |
| Event | Ordered event propagation and bounded replay; Kafka is not the long-term message history API |
| Connection | Live WebSockets, presence and device-to-gateway routing; Redis state is disposable |
| Control | Authorization, membership, durable metadata, conversation ownership and fencing |
| Media | Encrypted attachments in object storage, reached through signed direct client uploads |
| Encryption | Device-side E2EE, private keys, media encryption and attachment-key wrapping |

These are responsibilities, not six mandatory microservices. Unrelated small apps
can explain why particular planes or messaging contracts do not apply.

## Required messaging contracts

The architect specifies conversation sequencing and ownership, durable history,
offline per-device cursors, persistent idempotency, precise acknowledgement stages,
WebSocket routing, regional failover, client E2EE, and direct encrypted media uploads.

The critic checks concrete implementation details: sequence/epoch recovery, message
and dedup keys, bounded partitions, commit-log durability, replication placement,
crash-safe event publication, stale-owner fencing, sync cursors and expired history,
reconnect races, key recovery and attachment finalization. Product names or vague
promises such as "exactly once" are insufficient.

For every component, the review asks:

> If this component completely disappears right now, do I lose an acknowledged user message?

The answer must name surviving durable copies and the recovery path already
available at acknowledgement. Node, cluster and regional failure scopes are
different. Periodic backups, local quorum and asynchronous remote copies must not
be presented as proof of zero-loss regional failover. A design must also distinguish
retained ciphertext from the ability to recover the keys needed to read it.

## How approval works

1. Requirements analysis preserves the relevant reliability and encryption constraints.
2. Research and evaluation examine the guarantees needed for the assigned role.
3. Architecture generation puts plane labels in component categories, durability
   placement in deployment descriptions, per-component failure analysis in tradeoffs,
   and concrete messaging flows in implementation steps.
4. The critic returns ordinary JSON text against an internal schema naming every
   component ID, all six planes, and all nine messaging contracts. Separate
   responsibility and disappearance maps each require every component ID. Python converts
   this validated map into `ArchitectureReview`; public API models remain unchanged.
   Duplicate JSON keys and missing/extra review entries are rejected and retried.
5. Python blocks approval for failed checks, missing or duplicate component reviews,
   unknown components, omitted planes/contracts, or contradictory required changes,
   even if the critic sets `approved=true`. Component checks cannot be skipped as
   not applicable. Other justified omissions must include an explanation.
6. The existing revision pass receives these required changes; the revised design
   receives a fresh audit. Remaining problems keep the final design unapproved.

Revisions now generate only changed fields through an internal text JSON contract.
Python preserves untouched content, validates the complete merged plan, and gives
the full plan to the final critic. See [performance measurement](PERFORMANCE.md).

The code enforces coverage and verdict consistency. The model still performs the
semantic assessment; this is not a formal proof or fault-injection test of a deployed
messaging system. Evidence is saved for human inspection.

The original request and research evidence reach both critic passes, so a summarized
requirement cannot silently replace an explicit user constraint. Research excerpts
are bounded and balanced across queries for the local context window; the complete
source records are still saved. Downstream agents receive compact evaluation decisions
instead of repeated candidate descriptions. Token-limit failures receive explicit
shortening instructions on retry, with finish reason and output length logged.
The final audit is
saved in the existing architecture `tradeoffs` field and displayed separately under
**Decisions → Responsibility & durability review**. It is included in normal query
history and JSON exports. Public API models remain unchanged. PydanticAI still uses
plain text, `json.loads` and `model_validate`; no provider tool/structured output is used.

## Verification

From `backend`, run `python -m pytest -q` using the project virtual environment.
Set `ARCHPILOT_DATABASE_TESTS=1` to include isolated PostgreSQL integration tests.
The new regression cases cover each failed messaging contract, component loss or
misuse, omitted/duplicate reviews, contradictory approval, and justified non-messaging
scope. The mocked transport test also verifies the revision path and the unchanged
single-system/plain-text OpenAI-compatible request format.

With the configured local Bonsai server running and idle, this live negative test
reviews a deliberately unsafe design without altering saved user queries:

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\verify_responsibilities.py
```

It requires rejection of all nine unsafe messaging contracts. The full model audit
is saved locally in `.demo/responsibility-review.json` for inspection.

Verified on the configured Bonsai 2 27B: all seven fixture components were reviewed
and all nine unsafe contracts were rejected. The run took 858.3 seconds, including
one malformed-JSON attempt that recovered through the existing retry handler.
The backend suite passed 74 tests (including PostgreSQL integration checks), the
frontend suite passed 16, and TypeScript and the production build passed.

The real saved messaging query was also run through the complete pipeline after
bounding the model context. Round 4 (`24aff760-f9a6-47be-adbd-780d9137238f`) completed
in 1,457 seconds with 12 components and 39 audit findings. Six findings failed, so
the final design remains **unapproved**: message/media survival during regional
loss, five-year history planning, cross-region ACK/failover details, and group E2EE
key lifecycle still need concrete implementation details. Responsibility placement
passed for all six planes. This verifies that a completed generation is not silently
treated as a safe or approved design.

The original request, all four classified rounds, the full architecture, and the
final audit matched PostgreSQL through the frontend proxy. The Decisions view
displayed all 39 findings and six failures with no browser errors or horizontal
overflow. The interrupted third round remains recorded as failed.

Open the saved query at
`http://127.0.0.1:3000/?query=d8c3aa90-cafe-43b5-829e-87450f06909b`.
Recheck its persisted data with:

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\verify_query.py d8c3aa90-cafe-43b5-829e-87450f06909b
```

## Primary references checked

- [Kafka design and delivery guarantees](https://kafka.apache.org/43/design/design/):
  partition ordering, log replication, delivery semantics and retention.
- [ScyllaDB consistency levels](https://docs.scylladb.com/manual/stable/cql/consistency.html):
  which replicas respond, including local versus cross-datacenter consistency.
- [Signal Sesame](https://signal.org/docs/specifications/sesame/) and
  [Double Ratchet](https://signal.org/docs/specifications/doubleratchet/): device
  session management and established message encryption protocols.
- [S3 signed uploads](https://docs.aws.amazon.com/AmazonS3/latest/userguide/PresignedUrlUploadObject.html):
  delegated direct object uploads. Client encryption and ACK durability remain
  explicit application requirements.
