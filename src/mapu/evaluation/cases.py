"""Built-in benchmark cases for Priority 1 domains."""

from __future__ import annotations

from mapu.evaluation.types import (
    BenchmarkCase,
    BenchmarkDomain,
    ExpectedEntity,
    ExpectedProposition,
    ExpectedQueryHit,
)

LEGAL_CONTRACT_CLAUSE = BenchmarkCase(
    id="legal_001",
    domain=BenchmarkDomain.LEGAL,
    description="Purchase agreement with conditional obligation and defined term",
    source_text=(
        "Section 4.2 Delivery of Financial Statements. "
        "The Seller shall deliver to the Buyer audited financial statements "
        "within ninety (90) days of the Closing Date, provided that no Material "
        "Adverse Effect has occurred prior to such delivery date. "
        '"Material Adverse Effect" means any event, change, or condition that, '
        "individually or in the aggregate, has had or would reasonably be expected "
        "to have a material adverse effect on the business, assets, financial "
        "condition, or results of operations of the Company."
    ),
    expected_entities=(
        ExpectedEntity(text="Seller", kind="party"),
        ExpectedEntity(text="Buyer", kind="party"),
        ExpectedEntity(text="Company", kind="organization"),
    ),
    expected_propositions=(
        ExpectedProposition(
            normalized_text="Seller shall deliver audited financial statements within 90 days",
            predicate="deliver",
            subject="Seller",
        ),
    ),
    query_question="What are the Seller's delivery obligations?",
    expected_query_hits=(
        ExpectedQueryHit(proposition_text="deliver audited financial statements"),
    ),
    tags=("contract", "obligation", "defined_term"),
)

LEGAL_AMENDMENT = BenchmarkCase(
    id="legal_002",
    domain=BenchmarkDomain.LEGAL,
    description="Amendment superseding original clause",
    source_text=(
        "Amendment No. 1 to Credit Agreement\n\n"
        "Section 7.2(a) of the Credit Agreement is hereby deleted in its entirety "
        "and replaced with the following:\n\n"
        '"(a) The Borrower shall maintain a Consolidated Leverage Ratio of not '
        'greater than 4.50 to 1.00 as of the last day of each fiscal quarter."\n\n'
        "The original Section 7.2(a) provided that the Borrower shall maintain "
        "a Consolidated Leverage Ratio of not greater than 3.50 to 1.00."
    ),
    expected_entities=(
        ExpectedEntity(text="Borrower", kind="party"),
    ),
    expected_propositions=(
        ExpectedProposition(
            normalized_text="Consolidated Leverage Ratio not greater than 4.50",
            predicate="maintain",
            subject="Borrower",
        ),
    ),
    tags=("amendment", "supersession", "covenant"),
)

FINANCE_EARNINGS = BenchmarkCase(
    id="finance_001",
    domain=BenchmarkDomain.FINANCE,
    description="Earnings call with revenue guidance and actual results",
    source_text=(
        "Q3 2025 Earnings Call Transcript — TechCorp Inc.\n\n"
        "CEO: We are pleased to report revenue of $2.3 billion for the third "
        "quarter, representing a 15% year-over-year increase. Operating margin "
        "expanded to 28.5%, up from 24.1% in the prior year period.\n\n"
        "CFO: For the full year 2025, we are raising our revenue guidance to "
        "$9.0 billion to $9.2 billion, up from our previous range of $8.7 billion "
        "to $8.9 billion. We expect operating margins of 27% to 28% for the "
        "full year.\n\n"
        "Regarding our credit facility, we remain in compliance with all covenants. "
        "The Consolidated Leverage Ratio was 2.1x as of September 30, well within "
        "our 3.5x covenant limit."
    ),
    expected_entities=(
        ExpectedEntity(text="TechCorp Inc.", kind="organization"),
    ),
    expected_propositions=(
        ExpectedProposition(
            normalized_text="revenue of $2.3 billion for Q3 2025",
            predicate="reported_revenue",
            subject="TechCorp Inc.",
        ),
    ),
    query_question="What was TechCorp's Q3 2025 revenue?",
    expected_query_hits=(
        ExpectedQueryHit(proposition_text="revenue of $2.3 billion"),
    ),
    tags=("earnings", "guidance", "covenant"),
)

FINANCE_SEC_FILING = BenchmarkCase(
    id="finance_002",
    domain=BenchmarkDomain.FINANCE,
    description="10-K risk factor with quantitative metrics",
    source_text=(
        "Item 1A. Risk Factors\n\n"
        "Customer Concentration Risk. For the fiscal year ended December 31, 2025, "
        "our three largest customers accounted for approximately 45% of total "
        "revenue. Customer A represented 22% of revenue ($1.98 billion), "
        "Customer B represented 13% ($1.17 billion), and Customer C represented "
        "10% ($900 million). The loss of any of these customers, or a significant "
        "reduction in their purchases, could have a material adverse effect on "
        "our business."
    ),
    expected_entities=(
        ExpectedEntity(text="Customer A", kind="organization"),
        ExpectedEntity(text="Customer B", kind="organization"),
        ExpectedEntity(text="Customer C", kind="organization"),
    ),
    tags=("sec_filing", "risk_factor", "concentration"),
)

BIOMEDICAL_TRIAL = BenchmarkCase(
    id="biomedical_001",
    domain=BenchmarkDomain.BIOMEDICAL,
    description="Clinical trial results with statistical outcomes",
    source_text=(
        "Results of Phase III Randomized Controlled Trial\n\n"
        "Drug XR-42 versus placebo in patients with moderate-to-severe "
        "rheumatoid arthritis (N=1,247).\n\n"
        "Primary endpoint: ACR20 response at Week 24 was achieved by 67.3% "
        "of patients in the XR-42 group versus 31.2% in the placebo group "
        "(p < 0.001, OR 4.52, 95% CI 3.41-5.98).\n\n"
        "Secondary endpoint: Mean change in DAS28-CRP from baseline was "
        "-2.8 in the XR-42 group versus -1.1 in placebo (p < 0.001).\n\n"
        "Safety: Serious adverse events occurred in 8.2% of XR-42 patients "
        "versus 6.1% of placebo patients. Two cases of hepatotoxicity were "
        "observed in the XR-42 group (ALT > 5x ULN), both resolved upon "
        "discontinuation."
    ),
    expected_entities=(
        ExpectedEntity(text="XR-42", kind="drug"),
        ExpectedEntity(text="rheumatoid arthritis", kind="condition"),
    ),
    expected_propositions=(
        ExpectedProposition(
            normalized_text="XR-42 ACR20 response 67.3% versus placebo 31.2%",
            predicate="efficacy",
            subject="XR-42",
        ),
    ),
    query_question="What was the efficacy of XR-42 in rheumatoid arthritis?",
    expected_query_hits=(
        ExpectedQueryHit(proposition_text="ACR20 response"),
    ),
    tags=("clinical_trial", "rct", "efficacy", "safety"),
)

BIOMEDICAL_REVIEW = BenchmarkCase(
    id="biomedical_002",
    domain=BenchmarkDomain.BIOMEDICAL,
    description="Systematic review with conflicting evidence",
    source_text=(
        "Systematic Review: Omega-3 Fatty Acids and Cardiovascular Outcomes\n\n"
        "We identified 14 randomized controlled trials (N=112,059 participants). "
        "Meta-analysis showed a modest reduction in major adverse cardiovascular "
        "events (RR 0.92, 95% CI 0.87-0.98, p=0.008, I²=42%).\n\n"
        "However, subgroup analysis revealed significant heterogeneity. "
        "Trials using high-dose EPA (≥2g/day) showed significant benefit "
        "(RR 0.75, 95% CI 0.65-0.87), while trials using mixed EPA/DHA "
        "showed no significant effect (RR 0.98, 95% CI 0.91-1.06).\n\n"
        "The REDUCE-IT trial (N=8,179) was the primary driver of the "
        "overall positive result, and its findings have been debated due "
        "to the mineral oil placebo raising LDL-C in the control arm."
    ),
    expected_entities=(
        ExpectedEntity(text="Omega-3", kind="intervention"),
        ExpectedEntity(text="EPA", kind="intervention"),
    ),
    tags=("systematic_review", "meta_analysis", "conflicting_evidence"),
)

CODE_API_DOC = BenchmarkCase(
    id="code_001",
    domain=BenchmarkDomain.CODE,
    description="API documentation with function contracts and deprecation",
    source_text=(
        "# payment_service.py\n\n"
        "def process_payment(amount: Decimal, currency: str, "
        "idempotency_key: str) -> PaymentResult:\n"
        '    """Process a payment transaction.\n\n'
        "    Args:\n"
        "        amount: Must be positive (> 0). Maximum 999999.99.\n"
        "        currency: ISO 4217 currency code (e.g., 'USD', 'EUR').\n"
        "        idempotency_key: Unique key for deduplication. Must be UUID format.\n\n"
        "    Returns:\n"
        "        PaymentResult with transaction_id and status.\n\n"
        "    Raises:\n"
        "        ValueError: If amount <= 0 or currency is invalid.\n"
        "        DuplicatePaymentError: If idempotency_key was already used.\n"
        '    """\n\n'
        "# Deprecated: Use process_payment instead\n"
        "def make_payment(amount, currency):\n"
        '    """Deprecated in v3.0. Will be removed in v4.0.\n'
        "    Use process_payment() with an idempotency_key instead.\n"
        '    """\n'
        "    warnings.warn('make_payment is deprecated', DeprecationWarning)\n"
        "    return process_payment(Decimal(str(amount)), currency, str(uuid4()))\n"
    ),
    expected_entities=(
        ExpectedEntity(text="process_payment", kind="function"),
        ExpectedEntity(text="make_payment", kind="function"),
    ),
    expected_propositions=(
        ExpectedProposition(
            normalized_text="process_payment requires amount > 0",
            predicate="requires",
            subject="process_payment",
        ),
        ExpectedProposition(
            normalized_text="make_payment deprecated in v3.0",
            predicate="deprecated",
            subject="make_payment",
        ),
    ),
    query_question="What are the constraints on process_payment?",
    tags=("api", "contract", "deprecation"),
)

CODE_VULNERABILITY = BenchmarkCase(
    id="code_002",
    domain=BenchmarkDomain.CODE,
    description="Security advisory with CVE and affected versions",
    source_text=(
        "Security Advisory: CVE-2025-9876\n\n"
        "Affected Package: web-framework v2.0.0 through v2.4.3\n"
        "Fixed in: v2.4.4\n"
        "Severity: Critical (CVSS 9.1)\n"
        "Type: Remote Code Execution via template injection\n\n"
        "Description: A server-side template injection vulnerability exists "
        "in the render_template() function when user-controlled input is "
        "passed directly to the template engine without sanitization. "
        "An attacker can execute arbitrary code on the server by crafting "
        "a malicious template string.\n\n"
        "Mitigation: Upgrade to v2.4.4 or later. If upgrading is not "
        "immediately possible, ensure all user input is sanitized before "
        "passing to render_template()."
    ),
    expected_entities=(
        ExpectedEntity(text="web-framework", kind="library"),
        ExpectedEntity(text="CVE-2025-9876", kind="vulnerability"),
    ),
    tags=("cve", "security", "vulnerability"),
)

ALL_BENCHMARK_CASES: list[BenchmarkCase] = [
    LEGAL_CONTRACT_CLAUSE,
    LEGAL_AMENDMENT,
    FINANCE_EARNINGS,
    FINANCE_SEC_FILING,
    BIOMEDICAL_TRIAL,
    BIOMEDICAL_REVIEW,
    CODE_API_DOC,
    CODE_VULNERABILITY,
]


def get_cases_by_domain(domain: BenchmarkDomain) -> list[BenchmarkCase]:
    return [c for c in ALL_BENCHMARK_CASES if c.domain == domain]


def get_cases_by_tag(tag: str) -> list[BenchmarkCase]:
    return [c for c in ALL_BENCHMARK_CASES if tag in c.tags]
