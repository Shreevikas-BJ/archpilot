"""Internal review contract; the public architecture and critique schemas stay unchanged."""

from collections import Counter
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

from app.schemas import ArchitecturePlan, Critique

Plane = Literal["durable_data", "event", "connection", "control", "media", "encryption"]
MessagingConcern = Literal[
    "conversation_ordering",
    "durable_history",
    "offline_sync",
    "idempotency",
    "acknowledgements",
    "connection_routing",
    "region_failover",
    "client_e2ee",
    "direct_media_upload",
]


class ResponsibilityCheck(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    status: Literal["pass", "fail", "not_applicable"]
    evidence: str = Field(min_length=1)
    required_change: str = ""


class ComponentReview(BaseModel):
    component_id: str
    responsibility: ResponsibilityCheck
    disappearance: ResponsibilityCheck


class ArchitectureReview(Critique):
    """Generated as ordinary JSON text, never as tool or structured provider output."""

    components: list[ComponentReview]
    planes: dict[Plane, ResponsibilityCheck]
    messaging: dict[MessagingConcern, ResponsibilityCheck]


def finalize_review(
    architecture: ArchitecturePlan, review: ArchitectureReview
) -> tuple[Critique, list[str]]:
    """Require complete audit coverage and fail closed on any negative finding.

    This enforces review completeness/consistency, not the truth of model reasoning.
    Evidence remains visible so the user can inspect the semantic assessment.
    """
    changes = list(review.required_changes)
    notes: list[str] = []
    expected = {component.id for component in architecture.components}
    counts = Counter(item.component_id for item in review.components)
    for component_id in sorted(expected):
        if counts[component_id] != 1:
            changes.append(
                f"Provide exactly one responsibility and disappearance review for {component_id}."
            )
    for component_id in sorted(counts.keys() - expected):
        changes.append(f"Correct the review of unknown component {component_id}.")

    def check(label: str, result: ResponsibilityCheck, *, allow_na: bool = True) -> None:
        notes.append(f"Responsibility audit - {label} [{result.status}]: {result.evidence}")
        if result.status == "fail" or (result.status == "not_applicable" and not allow_na):
            changes.append(result.required_change or f"Resolve {label}: {result.evidence}")
        elif result.required_change:
            # A passing label cannot conceal a material correction in the same finding.
            changes.append(result.required_change)

    for item in review.components:
        check(f"{item.component_id} responsibility", item.responsibility, allow_na=False)
        check(f"{item.component_id} disappears", item.disappearance, allow_na=False)
    for name in get_args(Plane):
        if name not in review.planes:
            changes.append(f"Review the {name.replace('_', ' ')} plane, or explain its absence.")
        else:
            check(f"{name.replace('_', ' ')} plane", review.planes[name])
    for name in get_args(MessagingConcern):
        if name not in review.messaging:
            changes.append(f"Review {name.replace('_', ' ')}, or explain why it is not applicable.")
        else:
            check(name.replace("_", " "), review.messaging[name])
    changes = list(dict.fromkeys(changes))
    return (
        Critique(
            approved=review.approved and not changes,
            confidence=review.confidence,
            risks=review.risks,
            required_changes=changes,
            unnecessary_components=review.unnecessary_components,
        ),
        notes,
    )


RESPONSIBILITY_POLICY = """
Validate responsibilities and failure behavior, not just technology names. Apply relevant
planes to every design; a plane is a logical responsibility, not a demand for another service.
Small non-messaging applications need no Kafka, Redis, or distributed message database.
Distinguish these six planes, explicitly identifying any that are not applicable:
- durable_data: authoritative committed user records; for messaging, durable hot ciphertext
  history in a ScyllaDB/Cassandra-style message store, not Kafka retention or Redis caches.
- event: ordered propagation and bounded replay. Kafka is an ordered event backbone, not the
  long-term message database or the offline client's history API.
- connection: live WebSocket sessions and delivery. Redis holds disposable presence and
  device-to-gateway routing with TTLs; never authoritative messages or acknowledgement state.
- control: authentication, membership/authorization, configuration, conversation ownership,
  fencing epochs and durable device/cursor metadata. Separate authoritative state from caches.
- media: object storage/CDN for encrypted large attachments. App servers authorize short-lived,
  scoped signed direct uploads; clients send bytes directly to object storage, bypassing servers.
- encryption: encryption, decryption, identity/private keys and media key wrapping run on
  client devices. Servers route/store ciphertext and public key material, not plaintext or
  unwrapped content keys. TLS and server-side KMS encryption do not constitute client E2EE.

For a user messaging/chat system, explicitly specify all these contracts:
1. conversation_ordering: stable conversation_id routing/partition key; one fenced owner or
   sequencer assigns monotonic conversation sequence numbers. Persist the sequence and epoch;
   preserve order on retries, rebalance and failover; handle gaps. No global order claim. Kafka
   partition ordering or wall-clock timestamps alone do not order concurrent cross-region writes.
2. durable_history: message key (conversation_id, bounded time/size bucket, sequence), durable
   message_id dedup mapping, retention/deletion, replication factor, failure-domain placement,
   write/read consistency AND commit-log/fsync policy. A quorum response alone does not prove
   power-loss durability. Specify recovery sources for loss of a node, cluster and entire region.
3. offline_sync: durable per-device/per-conversation cursor, paginated reads from the message
   store, gap detection, reconnect/resume and duplicate-safe merging of live delivery with history.
   An expired cursor triggers defined full resync/retention handling, never silent loss. Live
   socket delivery is a hint; Kafka offsets and Redis presence are not client sync cursors.
4. idempotency: stable client-generated message_id scoped to sender/device + conversation;
   atomic durable uniqueness/dedup tied to the stored message and assigned sequence; retries
   return the original result across timeouts, restarts and regions. Bound dedup retention against
   the retry horizon. Describe crash recovery between durable storage and event publication:
   use supported atomic outbox/CDC with retention/reconciliation, or a log-first materializer
   with ACK gated on durable history. Do not claim a cross-system transaction or unsupported
   Cassandra/Scylla multi-partition atomic outbox. Avoid unqualified end-to-end exactly-once claims.
5. acknowledgements: distinguish transport receipt, durable server acceptance, recipient device
   delivery and read receipts. Show the precise durable commit/replication boundary before the
   user-visible sent/accepted ACK. Never ACK solely on a WebSocket write, Redis, or a Kafka append
   awaiting history persistence. Lost ACKs are retried with the same idempotency key. Stop
   accepting when the promised durability cannot be achieved; do not silently weaken quorum.
6. connection_routing: multiple devices per user mapped to gateway_id/connection_id/region with
   TTL/heartbeat and stale-session fencing; internal dispatch to the correct socket owner;
   reconnect rebuilds lost Redis routes and recovers history. Load-balancer affinity alone does
   not locate a recipient's gateway. Gateway/Redis loss may delay delivery, not erase sent messages.
7. region_failover: one conversation home region/owner at a time, consensus-backed lease/epoch,
   stale-owner fencing enforced on writes, sequencer high-water recovery and replication watermark
   before promotion. Explain split-brain prevention, RTO/RPO and partition behavior. Async remote
   replication or LOCAL_QUORUM is not zero-RPO regional failover. To preserve acknowledged
   messages through region disappearance, synchronously persist outside that region before ACK
   or refuse unsafe promotion/acknowledgement; label any weaker guarantee as an unmet requirement.
8. client_e2ee: an established reviewed protocol/library (e.g. Signal-family sessions or MLS for
   groups), client identity verification, per-device keys, group membership/key rotation, secure
   local key storage, offline sessions and device revocation. Explain recoverability if a device
   and its keys disappear: other authorized devices or explicitly client-encrypted key backup,
   never server-held plaintext keys. Do not invent cryptography or claim server plaintext search.
9. direct_media_upload: client creates a random attachment key, encrypts/authenticates bytes,
   uploads ciphertext directly with a scoped expiring signed URL (multipart when needed), and
   wraps/distributes the attachment key inside the client E2EE message. Authenticate object ID,
   integrity hash and metadata; finalize only after upload verification and the required durable
   replication. Define retry/orphan cleanup and download authorization. No backend encryption,
   media key wrapping, or proxying large uploads through application servers.

For EVERY component ask exactly: "If this component completely disappears right now, do I lose
an acknowledged user message?" Include clients, gateways, caches, logs, metadata, stores and media.
State the failure scope and the surviving durable replica/recovery path already available at ACK.
Replicas inside a disappeared cluster/region do not survive that scope. Distinguish temporary
unavailability from permanent loss and ciphertext survival from loss of its decryption keys.
A periodic backup cannot protect newer acknowledged messages. If data would be lost, the design
must add independently replicated durability before ACK or explicitly fail the review. For a
non-messaging system assess acknowledged writes against its stated durability/RPO requirements;
do not impose zero-RPO regional replication on an unrelated app that explicitly accepts data loss.
Explain when a component has no authoritative user data. Never invent a passing guarantee from
unspecified replication settings.
""".strip()
