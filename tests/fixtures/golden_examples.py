"""Golden test fixtures for the 30 hard examples.

Each example defines the rows needed to seed a minimal scenario and the expected
truth status after TruthPolicyV1.1 computation. These fixtures test the full
evidence → attestation → truth pipeline at the data level.

Format: GoldenExample dataclasses seeded through repositories in integration tests.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class HandleFixture:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    canonical_name: str = ""
    kind: str = ""


@dataclass(frozen=True)
class PropositionFixture:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    frame_type: str = "finding"
    subject: HandleFixture = field(default_factory=HandleFixture)
    predicate: str = ""
    object: HandleFixture | None = None
    value: dict | None = None
    polarity: bool = True
    modality: str | None = None
    valid_range: tuple[str | None, str | None] | None = None
    normalized_text: str = ""
    qualifiers: dict = field(default_factory=dict)
    semantic_key: str = ""


@dataclass(frozen=True)
class AttestationFixture:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    proposition_idx: int = 0
    stance: str = "asserts"
    extraction_method: str = "golden_fixture"
    extraction_confidence: float = 0.95
    attestation_strength: str | None = "direct_statement"
    authority_score: float = 0.8
    attestation_type: str | None = "first_party"
    document_type: str | None = None
    publication_context: str | None = None
    independence_group: str | None = None
    status: str = "accepted"


@dataclass(frozen=True)
class SituationFixture:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    kind: str = ""
    name: str = ""


@dataclass(frozen=True)
class SupersessionFixture:
    old_proposition_idx: int = 0
    new_proposition_idx: int = 1
    supersession_type: str = "amendment"
    effective_at: str = "2025-01-01T00:00:00Z"


@dataclass(frozen=True)
class ExpectedTruth:
    proposition_idx: int = 0
    situation_idx: int = 0
    expected_status: str = "accepted"


@dataclass(frozen=True)
class GoldenExample:
    code: str
    domain: str
    description: str
    handles: list[HandleFixture] = field(default_factory=list)
    propositions: list[PropositionFixture] = field(default_factory=list)
    situations: list[SituationFixture] = field(default_factory=list)
    attestations: list[AttestationFixture] = field(default_factory=list)
    supersessions: list[SupersessionFixture] = field(default_factory=list)
    expected_truth: list[ExpectedTruth] = field(default_factory=list)


# ============================================================
# LEGAL EXAMPLES
# ============================================================

L1 = GoldenExample(
    code="L1",
    domain="legal",
    description="Conditional obligation: Seller shall deliver audited financials within 90 days of Closing Date, provided no MAE",
    handles=[
        HandleFixture(canonical_name="Seller", kind="party"),
    ],
    propositions=[
        PropositionFixture(
            frame_type="obligation",
            predicate="deliver",
            normalized_text="Seller shall deliver audited financial statements within 90 days of Closing Date, provided no MAE",
            qualifiers={"condition": "no Material Adverse Effect has occurred", "temporal_qualifier": "within 90 days of Closing Date"},
            semantic_key="seller:deliver:audited_financials:section_4_2",
        ),
    ],
    situations=[SituationFixture(kind="contractual_terms", name="Purchase Agreement")],
    attestations=[
        AttestationFixture(stance="asserts", authority_score=0.88),
    ],
    expected_truth=[ExpectedTruth(expected_status="accepted")],
)

L3 = GoldenExample(
    code="L3",
    domain="legal",
    description="Nested exception: Assignment prohibited without consent, but Affiliate assignment allowed if Affiliate assumes obligations",
    handles=[
        HandleFixture(canonical_name="parties", kind="party"),
        HandleFixture(canonical_name="Agreement", kind="contract"),
    ],
    propositions=[
        PropositionFixture(
            frame_type="obligation",
            predicate="assign",
            polarity=False,
            modality="shall_not",
            normalized_text="Parties shall not assign the Agreement without prior written consent",
            qualifiers={"condition": "without prior written consent", "exception": {"action": "assign to Affiliate", "sub_condition": "Affiliate assumes all obligations"}},
            semantic_key="parties:assign:agreement:prohibition",
        ),
    ],
    situations=[SituationFixture(kind="contractual_terms", name="Assignment clause")],
    attestations=[
        AttestationFixture(stance="asserts", authority_score=0.88),
        AttestationFixture(proposition_idx=0, stance="conditions", authority_score=0.88, attestation_strength="inference"),
    ],
    expected_truth=[ExpectedTruth(expected_status="accepted")],
)

L5 = GoldenExample(
    code="L5",
    domain="legal",
    description="Split-scope judicial holding: breach for 2024 amendments, not for 2020 agreement",
    handles=[
        HandleFixture(canonical_name="Defendant Corp", kind="party"),
        HandleFixture(canonical_name="Confidentiality provisions", kind="legal_concept"),
    ],
    propositions=[
        PropositionFixture(
            frame_type="finding",
            predicate="breached",
            polarity=True,
            normalized_text="Defendant breached 2024 amendment confidentiality provisions",
            qualifiers={"scope": "2024 amendments"},
            semantic_key="defendant:breached:confidentiality:2024_amendments",
        ),
        PropositionFixture(
            frame_type="finding",
            predicate="breached",
            polarity=False,
            normalized_text="Defendant did NOT breach 2020 agreement confidentiality provisions",
            qualifiers={"scope": "2020 agreement"},
            semantic_key="defendant:breached:confidentiality:2020_agreement",
        ),
    ],
    situations=[SituationFixture(kind="court_findings", name="Court ruling on breach")],
    attestations=[
        AttestationFixture(proposition_idx=0, stance="asserts", authority_score=0.92, document_type="court_opinion"),
        AttestationFixture(proposition_idx=1, stance="asserts", authority_score=0.92, document_type="court_opinion"),
    ],
    expected_truth=[
        ExpectedTruth(proposition_idx=0, expected_status="accepted"),
        ExpectedTruth(proposition_idx=1, expected_status="accepted"),
    ],
)

# ============================================================
# FINANCE EXAMPLES
# ============================================================

F1 = GoldenExample(
    code="F1",
    domain="finance",
    description="Debt covenant ratio: Interest Coverage >= 3.0x",
    handles=[
        HandleFixture(canonical_name="Borrower", kind="party"),
    ],
    propositions=[
        PropositionFixture(
            frame_type="constraint",
            predicate="maintain",
            normalized_text="Borrower shall maintain Interest Coverage Ratio >= 3.0x",
            qualifiers={"ratio_type": "interest_coverage", "threshold": 3.0, "operator": ">="},
            semantic_key="borrower:maintain:icr:3.0x",
        ),
    ],
    situations=[SituationFixture(kind="contractual_terms", name="Credit agreement covenants")],
    attestations=[
        AttestationFixture(stance="asserts", authority_score=0.85),
    ],
    expected_truth=[ExpectedTruth(expected_status="accepted")],
)

F2 = GoldenExample(
    code="F2",
    domain="finance",
    description="Guidance vs actual: guidance in management_guidance situation, actual in audited_financials",
    handles=[
        HandleFixture(canonical_name="Company XYZ", kind="organization"),
    ],
    propositions=[
        PropositionFixture(
            frame_type="measurement",
            predicate="projects_revenue",
            normalized_text="Company XYZ projects revenue of $500M for FY2025",
            qualifiers={"metric": "revenue", "value": 500_000_000, "period": "FY2025"},
            semantic_key="xyz:projects_revenue:fy2025",
        ),
        PropositionFixture(
            frame_type="measurement",
            predicate="reported_revenue",
            normalized_text="Company XYZ reported revenue of $475M for FY2025",
            qualifiers={"metric": "revenue", "value": 475_000_000, "period": "FY2025"},
            semantic_key="xyz:reported_revenue:fy2025",
        ),
    ],
    situations=[
        SituationFixture(kind="management_guidance", name="Q1 2025 earnings call"),
        SituationFixture(kind="audited_financials", name="FY2025 10-K"),
    ],
    attestations=[
        AttestationFixture(proposition_idx=0, stance="reports", authority_score=0.60, publication_context="earnings_call"),
        AttestationFixture(proposition_idx=1, stance="asserts", authority_score=0.85, publication_context="official_filing"),
    ],
    expected_truth=[
        ExpectedTruth(proposition_idx=0, situation_idx=0, expected_status="reported"),
        ExpectedTruth(proposition_idx=1, situation_idx=1, expected_status="accepted"),
    ],
)

F5 = GoldenExample(
    code="F5",
    domain="finance",
    description="Triple amendment chain: threshold 3.0 -> 3.5 -> 4.0 (reverting to 3.5 after June 2026)",
    handles=[
        HandleFixture(canonical_name="Borrower", kind="party"),
    ],
    propositions=[
        PropositionFixture(
            frame_type="threshold",
            predicate="minimum_ratio",
            normalized_text="Interest coverage ratio threshold = 3.0x (original)",
            qualifiers={"threshold": 3.0},
            semantic_key="borrower:icr_threshold:original",
        ),
        PropositionFixture(
            frame_type="threshold",
            predicate="minimum_ratio",
            normalized_text="Interest coverage ratio threshold = 3.5x (Amendment 1)",
            qualifiers={"threshold": 3.5},
            semantic_key="borrower:icr_threshold:amendment1",
        ),
        PropositionFixture(
            frame_type="threshold",
            predicate="minimum_ratio",
            normalized_text="Interest coverage ratio threshold = 4.0x (Amendment 2, effective until June 2026)",
            qualifiers={"threshold": 4.0},
            valid_range=("2025-01-01", "2026-06-30"),
            semantic_key="borrower:icr_threshold:amendment2_active",
        ),
        PropositionFixture(
            frame_type="threshold",
            predicate="minimum_ratio",
            normalized_text="Interest coverage ratio threshold = 3.5x (Amendment 2, after June 2026)",
            qualifiers={"threshold": 3.5},
            valid_range=("2026-06-30", None),
            semantic_key="borrower:icr_threshold:amendment2_revert",
        ),
    ],
    situations=[SituationFixture(kind="contractual_terms", name="Credit agreement")],
    attestations=[
        AttestationFixture(proposition_idx=0, stance="asserts", authority_score=0.85),
        AttestationFixture(proposition_idx=1, stance="asserts", authority_score=0.85),
        AttestationFixture(proposition_idx=2, stance="asserts", authority_score=0.85),
        AttestationFixture(proposition_idx=3, stance="asserts", authority_score=0.85),
    ],
    supersessions=[
        SupersessionFixture(old_proposition_idx=0, new_proposition_idx=1, supersession_type="amendment", effective_at="2024-01-01T00:00:00Z"),
        SupersessionFixture(old_proposition_idx=1, new_proposition_idx=2, supersession_type="amendment", effective_at="2025-01-01T00:00:00Z"),
    ],
    expected_truth=[
        ExpectedTruth(proposition_idx=0, expected_status="superseded"),
        ExpectedTruth(proposition_idx=1, expected_status="superseded"),
        ExpectedTruth(proposition_idx=2, expected_status="accepted"),
        ExpectedTruth(proposition_idx=3, expected_status="accepted"),
    ],
)

F7 = GoldenExample(
    code="F7",
    domain="finance",
    description="Dynamic materiality threshold (5% of total assets)",
    handles=[
        HandleFixture(canonical_name="Company ABC", kind="organization"),
    ],
    propositions=[
        PropositionFixture(
            frame_type="threshold",
            predicate="materiality_threshold",
            normalized_text="Materiality threshold is 5% of total assets",
            qualifiers={"computation": "ratio_comparison", "numerator": "item_value", "denominator": "total_assets", "threshold": 0.05},
            semantic_key="abc:materiality:5pct_total_assets",
        ),
    ],
    situations=[SituationFixture(kind="audited_financials", name="Audit methodology")],
    attestations=[
        AttestationFixture(stance="asserts", authority_score=0.80),
    ],
    expected_truth=[ExpectedTruth(expected_status="accepted")],
)

# ============================================================
# BIOMEDICAL EXAMPLES
# ============================================================

B1 = GoldenExample(
    code="B1",
    domain="biomedical",
    description="Drug efficacy: single peer-reviewed study",
    handles=[
        HandleFixture(canonical_name="Drug X", kind="intervention"),
        HandleFixture(canonical_name="Hypertension", kind="condition"),
    ],
    propositions=[
        PropositionFixture(
            frame_type="finding",
            predicate="reduces",
            normalized_text="Drug X reduces systolic BP by mean 12mmHg in mild hypertension",
            qualifiers={"effect_size": {"mean_reduction": 12, "unit": "mmHg"}, "population": "mild_hypertension", "p_value": 0.001},
            semantic_key="drug_x:reduces:systolic_bp:mild_hypertension",
        ),
    ],
    situations=[SituationFixture(kind="study_results", name="Phase III trial results")],
    attestations=[
        AttestationFixture(stance="asserts", authority_score=0.80, attestation_type="peer_reviewed", publication_context="peer_reviewed_journal"),
    ],
    expected_truth=[ExpectedTruth(expected_status="accepted")],
)

B2 = GoldenExample(
    code="B2",
    domain="biomedical",
    description="Conflicting studies: Vitamin D and COVID severity",
    handles=[
        HandleFixture(canonical_name="Vitamin D supplementation", kind="intervention"),
        HandleFixture(canonical_name="COVID-19 severity", kind="endpoint"),
    ],
    propositions=[
        PropositionFixture(
            frame_type="finding",
            predicate="reduces",
            normalized_text="Vitamin D supplementation reduces COVID-19 severity",
            qualifiers={"study": "composite_view"},
            semantic_key="vitd:reduces:covid_severity",
        ),
    ],
    situations=[SituationFixture(kind="study_results", name="Vitamin D meta-view")],
    attestations=[
        AttestationFixture(
            stance="asserts", authority_score=0.65, extraction_confidence=0.85,
            attestation_type="peer_reviewed", independence_group="study_a",
        ),
        AttestationFixture(
            stance="denies", authority_score=0.78, extraction_confidence=0.85,
            attestation_type="peer_reviewed", independence_group="study_b",
        ),
    ],
    expected_truth=[ExpectedTruth(expected_status="contested")],
)

B4 = GoldenExample(
    code="B4",
    domain="biomedical",
    description="Drug interaction with multiple participants",
    handles=[
        HandleFixture(canonical_name="Warfarin", kind="drug"),
        HandleFixture(canonical_name="Aspirin", kind="drug"),
    ],
    propositions=[
        PropositionFixture(
            frame_type="finding",
            predicate="increases_risk_of",
            normalized_text="Concurrent Warfarin and Aspirin increases bleeding risk by 2.3x",
            qualifiers={"risk_ratio": 2.3, "outcome": "bleeding"},
            semantic_key="warfarin_aspirin:interaction:bleeding_risk",
        ),
    ],
    situations=[SituationFixture(kind="study_results", name="Drug interaction study")],
    attestations=[
        AttestationFixture(stance="asserts", authority_score=0.80, attestation_type="peer_reviewed"),
    ],
    expected_truth=[ExpectedTruth(expected_status="accepted")],
)

B5 = GoldenExample(
    code="B5",
    domain="biomedical",
    description="Retracted study",
    handles=[
        HandleFixture(canonical_name="Treatment Y", kind="intervention"),
        HandleFixture(canonical_name="Condition Z", kind="condition"),
    ],
    propositions=[
        PropositionFixture(
            frame_type="finding",
            predicate="cures",
            normalized_text="Treatment Y cures Condition Z",
            semantic_key="treatment_y:cures:condition_z",
        ),
        PropositionFixture(
            frame_type="retraction",
            predicate="retracted",
            normalized_text="Retraction notice: Treatment Y cures Condition Z has been retracted",
            semantic_key="treatment_y:cures:condition_z:retraction",
        ),
    ],
    situations=[SituationFixture(kind="study_results", name="Retracted study")],
    attestations=[
        AttestationFixture(proposition_idx=0, stance="asserts", authority_score=0.80, attestation_type="peer_reviewed"),
        AttestationFixture(
            proposition_idx=1, stance="denies", authority_score=0.70,
            document_type="retraction_notice", attestation_type="peer_reviewed",
        ),
    ],
    supersessions=[
        SupersessionFixture(old_proposition_idx=0, new_proposition_idx=1, supersession_type="retraction", effective_at="2025-06-01T00:00:00Z"),
    ],
    expected_truth=[ExpectedTruth(proposition_idx=0, expected_status="retracted")],
)

# ============================================================
# CODE EXAMPLES
# ============================================================

C3 = GoldenExample(
    code="C3",
    domain="code",
    description="CVE vulnerability with severity",
    handles=[
        HandleFixture(canonical_name="libfoo", kind="library"),
        HandleFixture(canonical_name="CVE-2025-1234", kind="vulnerability"),
    ],
    propositions=[
        PropositionFixture(
            frame_type="vulnerability",
            predicate="has_vulnerability",
            normalized_text="libfoo has critical RCE vulnerability CVE-2025-1234",
            qualifiers={"severity": "critical", "type": "remote_code_execution", "cvss": 9.8},
            semantic_key="libfoo:vuln:cve-2025-1234",
        ),
    ],
    situations=[SituationFixture(kind="security_assessment", name="CVE database")],
    attestations=[
        AttestationFixture(stance="asserts", authority_score=0.90, publication_context="cve_database"),
    ],
    expected_truth=[ExpectedTruth(expected_status="accepted")],
)

# ============================================================
# INTELLIGENCE EXAMPLES
# ============================================================

I1 = GoldenExample(
    code="I1",
    domain="intelligence",
    description="Multi-source corporate intelligence: beneficial ownership",
    handles=[
        HandleFixture(canonical_name="Company X", kind="organization"),
        HandleFixture(canonical_name="BVI", kind="jurisdiction"),
        HandleFixture(canonical_name="Person Y", kind="person"),
    ],
    propositions=[
        PropositionFixture(
            frame_type="relationship",
            predicate="incorporated_in",
            normalized_text="Company X is incorporated in BVI",
            semantic_key="company_x:incorporated_in:bvi",
        ),
        PropositionFixture(
            frame_type="relationship",
            predicate="is_director_of",
            normalized_text="Person Y is director of Company X",
            semantic_key="person_y:director_of:company_x",
        ),
        PropositionFixture(
            frame_type="relationship",
            predicate="controlled_by",
            normalized_text="Company X is controlled by Person Y (per leaked document)",
            semantic_key="company_x:controlled_by:person_y",
        ),
    ],
    situations=[SituationFixture(kind="corporate_intelligence", name="Company X investigation")],
    attestations=[
        AttestationFixture(proposition_idx=0, stance="asserts", authority_score=0.90, publication_context="government_registry"),
        AttestationFixture(proposition_idx=1, stance="asserts", authority_score=0.85, publication_context="government_registry"),
        AttestationFixture(proposition_idx=2, stance="reports", authority_score=0.35, publication_context="leaked_document"),
    ],
    expected_truth=[
        ExpectedTruth(proposition_idx=0, expected_status="accepted"),
        ExpectedTruth(proposition_idx=1, expected_status="accepted"),
        ExpectedTruth(proposition_idx=2, expected_status="reported"),
    ],
)

I2 = GoldenExample(
    code="I2",
    domain="intelligence",
    description="Temporal pattern detection: series of transactions",
    handles=[
        HandleFixture(canonical_name="Entity A", kind="organization"),
    ],
    propositions=[
        PropositionFixture(
            frame_type="event",
            predicate="transferred_funds",
            normalized_text="Entity A transferred funds to shell companies in 5 jurisdictions over 18 months",
            qualifiers={"pattern_type": "layering", "jurisdiction_count": 5, "time_period_months": 18},
            semantic_key="entity_a:transferred_funds:multi_jurisdiction",
        ),
    ],
    situations=[SituationFixture(kind="financial_intelligence", name="AML investigation")],
    attestations=[
        AttestationFixture(stance="asserts", authority_score=0.70, attestation_strength="observation"),
    ],
    expected_truth=[ExpectedTruth(expected_status="accepted")],
)

I3 = GoldenExample(
    code="I3",
    domain="intelligence",
    description="Adversarial disinformation: state media report",
    handles=[
        HandleFixture(canonical_name="Country Z", kind="state_actor"),
    ],
    propositions=[
        PropositionFixture(
            frame_type="event",
            predicate="claims",
            normalized_text="Country Z state media claims bioweapons labs in neighboring country",
            semantic_key="country_z:claims:bioweapons_labs",
        ),
    ],
    situations=[SituationFixture(kind="media_monitoring", name="State media claims")],
    attestations=[
        AttestationFixture(
            stance="reports", authority_score=0.25,
            document_type="state_media_report", attestation_strength="allegation",
        ),
    ],
    expected_truth=[ExpectedTruth(expected_status="reported")],
)


ALL_EXAMPLES: list[GoldenExample] = [
    L1, L3, L5, F1, F2, F5, F7, B1, B2, B4, B5, C3, I1, I2, I3,
]
