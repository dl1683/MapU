"""Shared types, enums, and protocols for MapU."""

from __future__ import annotations

from enum import StrEnum


class FrameType(StrEnum):
    OBLIGATION = "obligation"
    DEFINITION = "definition"
    FINDING = "finding"
    MEASUREMENT = "measurement"
    CONSTRAINT = "constraint"
    RELATIONSHIP = "relationship"
    EVENT = "event"
    EVENT_DEFINITION = "event_definition"
    POLICY = "policy"
    REPRESENTATION = "representation"
    RULE = "rule"
    THRESHOLD = "threshold"
    CLASSIFICATION = "classification"
    VULNERABILITY = "vulnerability"
    DEPRECATION = "deprecation"
    INTERFACE_CONTRACT = "interface_contract"
    PERFORMANCE_CLAIM = "performance_claim"
    DEPENDENCY = "dependency"
    STATUS = "status"


class Stance(StrEnum):
    ASSERTS = "asserts"
    DENIES = "denies"
    REPORTS = "reports"
    QUESTIONS = "questions"
    CONDITIONS = "conditions"


class AttestationStatus(StrEnum):
    CANDIDATE = "candidate"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    QUARANTINED = "quarantined"


class AttestationStrength(StrEnum):
    DIRECT_STATEMENT = "direct_statement"
    ALLEGATION = "allegation"
    INFERENCE = "inference"
    OBSERVATION = "observation"
    MEASUREMENT = "measurement"
    COMPUTATION = "computation"
    EXPERT_JUDGMENT = "expert_judgment"


class AttestationType(StrEnum):
    FIRST_PARTY = "first_party"
    THIRD_PARTY = "third_party"
    GOVERNMENT = "government"
    EXPERT_OPINION = "expert_opinion"
    PEER_REVIEWED = "peer_reviewed"
    SELF_REPORTED = "self_reported"
    HEARSAY = "hearsay"
    AUTOMATED = "automated"


class PublicationContext(StrEnum):
    OFFICIAL_FILING = "official_filing"
    PEER_REVIEWED_JOURNAL = "peer_reviewed_journal"
    COURT_OPINION = "court_opinion"
    REGULATORY_BULLETIN = "regulatory_bulletin"
    PRESS_RELEASE = "press_release"
    EARNINGS_CALL = "earnings_call"
    INTERNAL_DOCUMENT = "internal_document"
    LEAKED_DOCUMENT = "leaked_document"
    SOCIAL_MEDIA = "social_media"
    GOVERNMENT_REGISTRY = "government_registry"
    CVE_DATABASE = "cve_database"
    CODE_REPOSITORY = "code_repository"


class TruthStatus(StrEnum):
    ACCEPTED = "accepted"
    DENIED = "denied"
    CONTESTED = "contested"
    REPORTED = "reported"
    UNKNOWN = "unknown"
    RETRACTED = "retracted"
    SUPERSEDED = "superseded"


class ReviewStatus(StrEnum):
    AUTO_COMPUTED = "auto_computed"
    HUMAN_REVIEWED = "human_reviewed"
    NEEDS_REVIEW = "needs_review"
    OVERRIDDEN = "overridden"


class HandleStatus(StrEnum):
    ACTIVE = "active"
    MERGED = "merged"
    SPLIT = "split"


class IdentityDecision(StrEnum):
    SAME_ENTITY = "same_entity"
    DIFFERENT_ENTITY = "different_entity"
    UNCERTAIN = "uncertain"


class ChangesetStatus(StrEnum):
    PROPOSED = "proposed"
    AUTO_APPLIED = "auto_applied"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"
    ROLLBACK_FAILED = "rollback_failed"


class ActorType(StrEnum):
    HUMAN = "human"
    AI_AGENT = "ai_agent"
    SYSTEM = "system"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GapSeverity(StrEnum):
    CRITICAL = "critical"
    MODERATE = "moderate"
    MINOR = "minor"


class GapStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class GapTargetType(StrEnum):
    PROPOSITION = "proposition"
    HANDLE = "handle"


class ComputationSpecStatus(StrEnum):
    CANDIDATE = "candidate"
    APPROVED = "approved"
    DEPRECATED = "deprecated"


class TruthBasisRole(StrEnum):
    SUPPORTING = "supporting"
    CONTRADICTING = "contradicting"
    NEUTRAL = "neutral"
