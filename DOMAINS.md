# MapU — Domain Research Reference

This document catalogs 37 use cases across 9 macro-domains that MapU's architecture is designed to handle. This is a **research reference**, not a configuration guide — MapU is domain-invariant and requires no domain-specific setup.

The purpose of this document is to:
- Ground architectural decisions in real-world reasoning patterns
- Ensure the universal abstractions (assertions, handles, authority, temporal validity, gaps) cover every known use case
- Identify the hardest reasoning patterns so the kernel handles them natively
- Serve as a validation checklist — if the architecture can't handle a use case listed here, the architecture has a gap

---

## I. Legal (6 profiles)

### 1. Litigation (Civil)
- **Documents:** Complaints, answers, motions, depositions, exhibits, discovery, expert reports, court orders, settlement agreements
- **Entities:** Parties, claims, causes of action, damages, deadlines, motions, rulings
- **Authority:** SCOTUS opinion > Circuit > District > statutes > regulations > expert testimony > party assertions
- **Temporal:** Filing dates, statute of limitations, procedural deadlines, superseding orders
- **Reasoning pattern:** Issue-proof-evidence chains — does this fact pattern satisfy each element of this cause of action?
- **Distinct need:** Gap analysis — which elements of a claim lack supporting evidence

### 2. Regulatory Compliance
- **Documents:** Regulations (CFR, EU directives), guidance documents, enforcement actions, internal policies, audit reports, regulator correspondence
- **Entities:** Rules, obligations, exceptions, safe harbors, enforcement actions, compliance controls
- **Authority:** Statute > regulation > agency guidance > no-action letters > industry practice
- **Temporal:** Effective dates, phase-in periods, sunset clauses, amendment histories
- **Reasoning pattern:** Obligation mapping — given business activity X, which rules apply and are we in compliance?
- **Distinct need:** Change detection — when regulations update, which internal controls are affected?

### 3. Contract Analysis (M&A / Commercial)
- **Documents:** Master agreements, amendments, side letters, schedules, exhibits, term sheets, closing checklists, board resolutions
- **Entities:** Defined terms, parties, obligations, conditions precedent, representations & warranties, indemnities, covenants
- **Authority:** Executed agreements > term sheets > email correspondence > oral representations
- **Temporal:** Execution dates, amendment chains (v1 → v2 → side letter), closing conditions, earn-out periods
- **Reasoning pattern:** Cross-reference resolution — Section 4.2 references Schedule A which references the Base Agreement amended by...
- **Distinct need:** Amendment chain tracking across multiple documents

### 4. Intellectual Property / Patent
- **Documents:** Patent applications, prior art, office actions, responses, continuations, interference proceedings, licensing agreements
- **Entities:** Claims, claim elements, prior art references, inventors, assignees, prosecution history events
- **Authority:** Issued patents > published applications > non-patent literature > examiner rejections
- **Temporal:** Priority dates, filing dates, publication dates, expiry dates, prosecution history estoppel
- **Reasoning pattern:** Novelty/obviousness — does any combination of prior art references disclose every element of claim 1?
- **Distinct need:** Claim chart mapping — element-by-element comparison against prior art

### 5. Immigration Law
- **Documents:** Petitions, evidence packages, RFEs, approvals/denials, country condition reports, degrees, employment letters
- **Entities:** Petitioners, beneficiaries, visa categories, evidence items, regulatory requirements per category
- **Authority:** Statutes > regulations > AAO precedent > USCIS policy manual > field office practice
- **Temporal:** Filing windows, priority dates (can span decades), policy changes, visa bulletin movement
- **Reasoning pattern:** Eligibility mapping — does this evidence package satisfy each requirement for this visa category?
- **Distinct need:** Evidence sufficiency analysis against category-specific regulatory checklists

### 6. Tax Law
- **Documents:** Tax code sections, treasury regulations, revenue rulings, private letter rulings, tax court opinions, treaty provisions
- **Entities:** Taxpayers, transactions, income types, deductions, credits, elections, reporting obligations
- **Authority:** IRC > regulations > revenue rulings > PLRs (non-precedential) > tax court cases
- **Temporal:** Tax years, effective dates, carryforward/carryback periods, statute of limitations
- **Reasoning pattern:** Transaction characterization — how is this classified and what consequences follow?
- **Distinct need:** Multi-jurisdiction interaction (federal + state + treaty)

---

## II. Finance (7 profiles)

### 7. Investment Banking / M&A Due Diligence
- **Documents:** CIMs, financial statements, tax returns, material contracts, management presentations, data room documents (hundreds to thousands)
- **Entities:** Target companies, acquirers, financial metrics, risks, synergies, deal terms, material issues
- **Authority:** Audited financials > management-prepared > projections > broker estimates
- **Temporal:** Historical periods, projection periods, deal timeline, diligence phases
- **Reasoning pattern:** Risk flagging — across 2,000 data room documents, what material risks exist?
- **Distinct need:** Red flag detection at scale with tight timelines

### 8. Equity Research / Hedge Fund Analysis
- **Documents:** 10-Ks, 10-Qs, earnings transcripts, investor presentations, sell-side research, industry reports, alternative data
- **Entities:** Companies, metrics (revenue, EBITDA, margins), guidance figures, management commentary, industry drivers
- **Authority:** SEC filings > earnings transcripts > sell-side research > news > social media
- **Temporal:** Quarterly/annual periods, guidance updates, estimate revisions, fiscal year misalignments
- **Reasoning pattern:** Thesis construction — is management's guidance achievable given historical trends?
- **Distinct need:** Tracking what management said vs. what happened across quarters

### 9. Credit Analysis / Lending
- **Documents:** Credit agreements, financial covenants, borrowing base certificates, compliance certificates, appraisals
- **Entities:** Borrowers, guarantors, collateral, covenants, financial ratios, events of default, waivers
- **Authority:** Executed credit agreements > compliance certificates > borrower representations > market data
- **Temporal:** Covenant testing periods, maturity dates, amendment dates, waiver expiration
- **Reasoning pattern:** Covenant compliance — is the borrower in compliance as of this testing date?
- **Distinct need:** Covenant tracking across amendments — same ratio test modified multiple times

### 10. Insurance Underwriting & Claims
- **Documents:** Applications, policies, endorsements, claim forms, medical records, police reports, adjuster notes, expert opinions
- **Entities:** Policyholders, insureds, coverages, exclusions, deductibles, sub-limits, claims, losses
- **Authority:** Policy language > endorsements > regulatory requirements > industry practice > adjuster judgment
- **Temporal:** Policy periods, occurrence dates, reporting dates, claim development over time
- **Reasoning pattern:** Coverage determination — does this loss fall within coverage considering all exclusions and endorsements?
- **Distinct need:** Policy stacking — multiple policies and endorsements interact to determine actual coverage

### 11. Audit / Accounting
- **Documents:** Financial statements, workpapers, management representations, internal controls docs, audit programs, sampling results
- **Entities:** Accounts, assertions (completeness, existence, valuation, rights, presentation), controls, findings
- **Authority:** GAAP/IFRS > audit standards (PCAOB/ISA) > firm methodology > professional judgment
- **Temporal:** Audit periods, interim vs. year-end, subsequent events, restatement history
- **Reasoning pattern:** Assertion testing — for this account, do we have sufficient evidence for each assertion?
- **Distinct need:** Mapping evidence to specific audit assertions at the account level

### 12. SEC Compliance / Regulatory Filings
- **Documents:** Prospectuses, registration statements, proxy statements, 8-Ks, comment letters, response letters, no-action letters
- **Entities:** Issuers, securities, disclosure requirements, risk factors, material events, officer certifications
- **Authority:** Securities laws > SEC rules > staff guidance > comment letter precedent > market practice
- **Temporal:** Filing deadlines, effective dates, periodic reporting calendar
- **Reasoning pattern:** Disclosure adequacy — given this event, have we disclosed everything required?
- **Distinct need:** Comment letter pattern analysis — what does SEC staff typically flag?

### 13. ESG / Sustainability Reporting
- **Documents:** Sustainability reports, CDP questionnaires, TCFD disclosures, EU CSRD reports, scope 1/2/3 calculations, supply chain disclosures
- **Entities:** Metrics (emissions, water, waste), targets, frameworks (GRI, SASB, ISSB), controversies
- **Authority:** Regulated disclosures > third-party audited > self-reported > estimated > modeled
- **Temporal:** Reporting years, target baselines, milestone years, framework version changes
- **Reasoning pattern:** Consistency checking — are numbers consistent across CDP, sustainability report, and 10-K?
- **Distinct need:** Cross-framework reconciliation (same metric reported differently across GRI, SASB, ISSB)

---

## III. Biomedical & Life Sciences (5 profiles)

### 14. Drug Discovery / Pharmaceutical R&D
- **Documents:** Research papers, assay results, compound databases, patent filings, preclinical study reports, competitor pipeline data
- **Entities:** Compounds, targets, pathways, mechanisms of action, efficacy/toxicity signals, disease models
- **Authority:** Peer-reviewed > preprint > internal lab results > computational predictions > expert opinion
- **Temporal:** Discovery timelines, patent dates, publication dates, competitive landscape evolution
- **Reasoning pattern:** Mechanism inference — given binding assays, transcriptomic data, and pathway maps, what is the likely MOA?
- **Distinct need:** Multi-modal evidence integration (chemical structures + genomic data + literature)

### 15. Clinical Trials / Regulatory Submissions
- **Documents:** Protocols, investigator brochures, CSRs, SAE reports, FDA/EMA guidance, ICH guidelines, NDA/BLA modules (CTD format)
- **Entities:** Studies, endpoints, patient populations, adverse events, efficacy results, regulatory milestones
- **Authority:** Phase III RCT > Phase II > Phase I > preclinical > case reports
- **Temporal:** Study dates, submission dates, PDUFA dates, label revision dates
- **Reasoning pattern:** Benefit-risk assessment — across all studies, does efficacy outweigh safety signals?
- **Distinct need:** CTD module cross-referencing — Module 2.7 must be consistent with Module 5

### 16. Systematic Reviews / Meta-Analysis
- **Documents:** Thousands of papers, protocols, PRISMA diagrams, risk-of-bias assessments, forest plots
- **Entities:** Studies, PICO elements, effect sizes, confidence intervals, bias domains
- **Authority:** RCT > cohort > case-control > case series > expert opinion (Oxford hierarchy)
- **Temporal:** Publication dates, study conduct dates, search update dates
- **Reasoning pattern:** Evidence synthesis — across qualifying studies, what is the pooled effect and heterogeneity?
- **Distinct need:** PICO extraction at scale + risk-of-bias assessment + quantitative pooling

### 17. Genomics / Precision Medicine
- **Documents:** Variant databases (ClinVar, gnomAD), functional studies, clinical case reports, ACMG guidelines
- **Entities:** Variants, genes, diseases, functional evidence categories (PS/PM/PP/BS/BP per ACMG)
- **Authority:** ACMG criteria > ClinVar expert panels > functional data > computational predictions
- **Temporal:** Reclassification history (VUS → pathogenic), new evidence updates
- **Reasoning pattern:** Variant classification — does this variant meet ACMG criteria for pathogenic/likely pathogenic?
- **Distinct need:** Combining population frequency + functional studies + clinical observations per ACMG framework

### 18. Pharmacovigilance / Post-Market Surveillance
- **Documents:** FAERS/VAERS reports, published case reports, PSURs, signal detection analyses, REMS documents
- **Entities:** Products, adverse events (MedDRA), patients, reporters, signal statistics (PRR, EBGM)
- **Authority:** Confirmed case with positive dechallenge/rechallenge > well-documented > spontaneous report > literature case
- **Temporal:** Reporting dates, onset dates, exposure windows, signal detection windows
- **Reasoning pattern:** Signal detection — is observed reporting rate above expected background with biological plausibility?
- **Distinct need:** Deduplication across reporting systems + causality assessment (Naranjo algorithm)

---

## IV. Code & Software Engineering (4 profiles)

### 19. Large Codebase Understanding
- **Documents:** Source files, commit history, PRs, issues, design docs, ADRs, API docs, dependency manifests
- **Entities:** Modules, classes, functions, types, dependencies, call graphs, data flows
- **Authority:** Running code > tests > type system > comments > external docs > commit messages
- **Temporal:** Git history, branch state, deprecation timelines, version releases
- **Reasoning pattern:** Impact analysis — if I change this interface, what breaks?
- **Distinct need:** Static analysis integration (ASTs, type graphs, call graphs) as structured knowledge

### 20. Security Audit / Vulnerability Analysis
- **Documents:** Source code, dependency manifests, CVE databases, OWASP guidelines, pentest reports, threat models
- **Entities:** Vulnerabilities, attack surfaces, data flows, trust boundaries, CVEs, CVSS scores
- **Authority:** CVE/NVD > vendor advisory > security researcher report > automated scan result
- **Temporal:** Disclosure dates, patch dates, exploit availability dates, scan dates
- **Reasoning pattern:** Attack path analysis — given entry points and data flows, what are viable attack paths?
- **Distinct need:** Taint tracking across code + dependency graph + known CVE mapping

### 21. Compliance-as-Code (SOC2, HIPAA, FedRAMP)
- **Documents:** Control frameworks, policies, procedure docs, evidence artifacts, audit reports, configuration files
- **Entities:** Controls, requirements, evidence items, systems, data classifications, gaps
- **Authority:** Regulatory requirement > framework control > organizational policy > implementation evidence
- **Temporal:** Audit periods, evidence windows, remediation deadlines, framework version changes
- **Reasoning pattern:** Control mapping — for each control, do we have current evidence of implementation?
- **Distinct need:** Cross-framework mapping (same control satisfies SOC2 CC6.1 AND HIPAA 164.312(a)(1))

### 22. Incident Post-Mortem / SRE
- **Documents:** Alert logs, runbooks, chat transcripts, metrics, deployment logs, config changes, previous post-mortems
- **Entities:** Services, dependencies, failure modes, symptoms, root causes, contributing factors, SLOs
- **Authority:** Metrics/logs > deployment records > observability data > human recollection
- **Temporal:** Precise timestamps (ms-level), deployment windows, TTD/TTR/TTM
- **Reasoning pattern:** Causal chain reconstruction — what sequence of events led from deploy X to customer impact Y?
- **Distinct need:** Timeline reconstruction with multi-source correlation at precise timestamps

---

## V. Intelligence & Investigations (4 profiles)

### 23. Open Source Intelligence (OSINT)
- **Documents:** Social media, news articles, government filings, satellite imagery analysis, corporate registrations, domain records
- **Entities:** Persons, organizations, locations, events, relationships, aliases, communication patterns
- **Authority:** Government records > verified journalism > social media (corroborated) > anonymous sources
- **Temporal:** Publication dates, event dates, relationship timelines, activity patterns
- **Reasoning pattern:** Entity resolution + relationship mapping across jurisdictions and identities
- **Distinct need:** Adversarial source handling. Confirmation bias is the primary epistemic risk.

### 24. Corporate Investigations / Fraud
- **Documents:** Financial records, email archives, chat logs, bank statements, corporate filings, whistleblower reports
- **Entities:** Persons, accounts, transactions, communications, shell entities, beneficial owners
- **Authority:** Bank records > corporate filings > authenticated email/chat > witness statements > tips
- **Temporal:** Transaction timelines, communication sequences, filing dates, statute of limitations
- **Reasoning pattern:** Pattern detection — do these transaction patterns constitute a scheme?
- **Distinct need:** Follow-the-money graph traversal + communication timeline correlation

### 25. Investigative Journalism
- **Documents:** Leaked documents (Panama/Pandora Papers scale), public records, financial filings, interview transcripts, court records
- **Entities:** Persons, entities, jurisdictions, financial flows, beneficial ownership chains
- **Authority:** Verified documents > multi-source corroboration > single-source claims
- **Temporal:** Document dates, entity creation/dissolution, publication embargoes
- **Reasoning pattern:** Connection discovery — what links this person to this entity through N intermediaries?
- **Distinct need:** Cross-jurisdiction entity resolution (same entity, different registries, different names)

### 26. Threat Intelligence / Cybersecurity
- **Documents:** Threat reports, IOC feeds, malware analysis, MITRE ATT&CK, vulnerability advisories, dark web monitoring
- **Entities:** Threat actors, campaigns, TTPs, IOCs, vulnerabilities, affected systems
- **Authority:** First-party observation > trusted ISAC > vendor report > open-source feed
- **Temporal:** Campaign timelines, IOC validity windows, TTP evolution
- **Reasoning pattern:** Attribution + prediction — based on IOCs and TTPs, which actor, and what next?
- **Distinct need:** IOC decay — indicators go stale. System must model indicator half-life.

---

## VI. Engineering & Construction (3 profiles)

### 27. Construction Project Management
- **Documents:** Specs, drawings, RFIs, submittals, change orders, daily logs, inspection reports, punch lists, contracts
- **Entities:** Spec sections, drawing references, RFIs, submittals, materials, trades, schedule activities
- **Authority:** Contract documents > approved submittals > RFI responses > field directives > daily logs
- **Temporal:** Schedule dates, submittal deadlines, substantial completion, change order effective dates
- **Reasoning pattern:** Cross-reference resolution — this RFI references spec 03 30 00 which conflicts with drawing S-401
- **Distinct need:** Drawing-spec-RFI cross-referencing with conflict detection

### 28. Aerospace / Defense Requirements Traceability
- **Documents:** System requirements, subsystem specs, interface control documents, test procedures, verification matrices, DO-178C artifacts
- **Entities:** Requirements (shall statements), verification methods, test cases, design elements, traceability links
- **Authority:** System-level req > subsystem req > derived req > design choice > test result
- **Temporal:** Baseline versions, change requests, configuration item history
- **Reasoning pattern:** Coverage analysis — is every shall-statement traced to a verification method that has been executed?
- **Distinct need:** Bidirectional traceability — requirement ↔ test, both directions

### 29. Manufacturing Quality / ISO Compliance
- **Documents:** Process specs, work instructions, inspection records, CAPA reports, audit findings, supplier certificates, calibration records
- **Entities:** Products, processes, non-conformances, root causes, corrective actions, calibration status
- **Authority:** Standard (ISO/AS9100) > approved process > inspection record > operator note
- **Temporal:** Calibration due dates, CAPA timelines, audit cycles, shelf life
- **Reasoning pattern:** Non-conformance trending — across 200 NCRs, what are the systemic root causes?
- **Distinct need:** CAPA effectiveness tracking — did the corrective action prevent recurrence?

---

## VII. Government & Policy (3 profiles)

### 30. Legislative Analysis
- **Documents:** Bills, amendments, committee reports, floor debates, CBO scores, lobbying disclosures, hearing testimonies
- **Entities:** Bills, provisions, sponsors, committees, voting records, affected statutes, stakeholder positions
- **Authority:** Enacted law > committee report > CBO score > floor debate > lobbying disclosure
- **Temporal:** Introduction, markup, floor vote, conference, enactment; amendment history within a session
- **Reasoning pattern:** Impact analysis — if this bill passes, which existing statutes change and how?
- **Distinct need:** Redline tracking — showing exactly what text in existing law changes

### 31. Government Procurement / Contracting
- **Documents:** Solicitations (RFPs/RFQs), proposals, SOWs, CDRLs, contract mods, past performance reports, FAR/DFARS clauses
- **Entities:** Requirements, CLINs, deliverables, evaluation criteria, offerors, contract mods, applicable clauses
- **Authority:** FAR/DFARS > solicitation > contracting officer determination > past performance evaluation
- **Temporal:** Solicitation timeline, proposal deadlines, periods of performance, option periods, mod effective dates
- **Reasoning pattern:** Compliance checking — does this proposal address every requirement in Section L/M?
- **Distinct need:** Clause flow-down — which FAR clauses apply and flow to subcontractors?

### 32. Regulatory Impact Assessment
- **Documents:** Proposed rules, economic analyses, public comments (thousands), agency responses, environmental impact statements
- **Entities:** Proposed provisions, affected populations, cost/benefit estimates, alternatives, commenters
- **Authority:** Statutory mandate > economic analysis > public comment (aggregated) > individual comment
- **Temporal:** Notice-and-comment timeline, effective dates, compliance phase-in
- **Reasoning pattern:** Comment synthesis — across 10,000 comments, what are the distinct substantive objections?
- **Distinct need:** Comment deduplication and clustering at massive scale

---

## VIII. Academic & Research (3 profiles)

### 33. Literature Review / Research Synthesis
- **Documents:** Papers, preprints, conference proceedings, dissertations, technical reports, datasets, code repos
- **Entities:** Papers, authors, methods, datasets, results, claims, citations, research gaps
- **Authority:** Peer-reviewed journal > conference > preprint > technical report > blog. Impact factor, citation count, replication status.
- **Temporal:** Publication dates, retraction dates, correction dates, field evolution
- **Reasoning pattern:** Gap identification — what's been studied, what methods tried, what remains unexplored?
- **Distinct need:** Claim tracking across papers — Paper A claims X, Paper B contradicts, Paper C replicates A

### 34. Grant Proposal / Funding Analysis
- **Documents:** RFAs, funded project abstracts (NIH RePORTER), progress reports, review criteria, study section rosters
- **Entities:** Programs, PIs, institutions, funded amounts, study sections, review scores, research areas
- **Authority:** Funding agency guidelines > study section review > program officer guidance
- **Temporal:** Funding cycles, project periods, renewal dates
- **Reasoning pattern:** Competitive landscape — who is funded, what approaches, where is white space?
- **Distinct need:** Portfolio analysis — full funding landscape for a research area

### 35. Standards Development
- **Documents:** Draft standards, committee ballots, public comments, technical reports, existing standards, meeting minutes
- **Entities:** Normative clauses, definitions, conformance criteria, ballot comments, dispositions
- **Authority:** Published standard > committee draft > technical report > individual contribution
- **Temporal:** Revision cycles (5-10 years), ballot deadlines, publication dates
- **Reasoning pattern:** Consistency checking — does this new clause conflict with existing or related standards?
- **Distinct need:** Cross-standard dependency tracking

---

## IX. Healthcare Operations & Supply Chain (2 profiles)

### 36. Clinical Case Management / EHR Reasoning
- **Documents:** Progress notes, lab results, imaging reports, medication lists, referral letters, discharge summaries
- **Entities:** Patients, diagnoses (ICD), medications, procedures (CPT), providers, lab values, vitals
- **Authority:** Lab result > imaging > specialist note > primary care note > patient self-report
- **Temporal:** Encounter dates, medication start/stop, lab trends, disease progression
- **Reasoning pattern:** Clinical reasoning — given history, labs, and medications, what is the differential?
- **Distinct need:** Longitudinal patient timeline with multi-provider reconciliation

### 37. Supply Chain Risk & Trade Compliance
- **Documents:** Supplier audits, shipping manifests, customs declarations, sanctions lists, trade agreements, certificates of origin
- **Entities:** Suppliers, products, countries, trade routes, sanctions entities, HS codes, compliance certificates
- **Authority:** Government sanctions list > customs record > audit finding > supplier self-declaration
- **Temporal:** Sanctions updates, trade agreement dates, audit validity periods, certificate expiration
- **Reasoning pattern:** Risk propagation — if tier-2 supplier is sanctioned, which products are affected?
- **Distinct need:** Multi-tier supply chain graph traversal with sanctions screening at every node

---

## What This Research Tells Us About Architecture

Looking across all 37 use cases, the universal abstractions MapU needs are:

1. **Assertions** — every domain produces claims/facts/findings that need tracking with provenance
2. **Handles** — every domain has canonical entities (parties, genes, functions, companies) that appear under different names across documents
3. **Authority** — every domain has a credibility hierarchy, but the system must infer it from source characteristics rather than requiring configuration
4. **Temporal validity** — every domain has facts that evolve, get superseded, or expire
5. **Cross-document references** — every domain has documents that reference each other
6. **Gaps** — every domain has missing evidence, unresolved contradictions, and unanswered questions
7. **Derivation chains** — every domain has conclusions derived from other claims, and those chains must be traceable
8. **Confidence** — every domain has uncertainty, and the system must represent it honestly

If MapU's invariant kernel handles all eight of these well, it handles every use case in this document without domain-specific code.
