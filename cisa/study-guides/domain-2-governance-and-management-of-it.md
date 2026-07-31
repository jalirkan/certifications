# CISA Domain 2 — Governance and Management of IT

**Weight: 18% of the exam.**

Structure below follows ISACA's published CISA Exam Content Outline, verified 2026-07-30 at
<https://www.isaca.org/credentialing/cisa/cisa-exam-content-outline>. The 11 topics are ISACA's;
the notes are mine.

**Exam format** (verified same date): 150 multiple-choice questions, 240 minutes, scaled score 200–800, 450 to pass.

> This domain is where "who decided this, and who is answerable for it" beats every technical
> consideration. Domain 2 answers are rarely about whether something works. They are about whether
> the right person authorized it, owns it, and is being held to account for it.

---

## How to use this guide

Update the **Status** column as you go. The drill tool reads none of this — it is yours to mark up.

| Mark | Meaning |
|------|---------|
| `[ ]` | Not started |
| `[~]` | Read it, shaky — keep drilling |
| `[x]` | Solid: can explain it cold and reliably pick the auditor's answer |

Suggested loop per topic: read the notes → `python drill.py drill --topic "<topic>" -n 8` →
mark `[~]` → return two days later in `--mode due` → mark `[x]` when you are hitting ~85%+ without hesitation.

---

## Progress tracker

### Part A — IT Governance

| # | Topic | Status | Last drilled | Accuracy |
|---|-------|--------|--------------|----------|
| A1 | Laws, Regulations, and Industry Standards | `[ ]` | | |
| A2 | Organizational Structure, IT Governance, and IT Strategy | `[ ]` | | |
| A3 | IT Policies, Standards, Procedures and Practices | `[ ]` | | |
| A4 | Enterprise Architecture and Considerations | `[ ]` | | |
| A5 | Enterprise Risk Management | `[ ]` | | |
| A6 | Privacy Program and Principles | `[ ]` | | |
| A7 | Data Governance and Classification | `[ ]` | | |

### Part B — IT Management

| # | Topic | Status | Last drilled | Accuracy |
|---|-------|--------|--------------|----------|
| B1 | IT Resource Management | `[ ]` | | |
| B2 | IT Vendor Management | `[ ]` | | |
| B3 | IT Performance Monitoring and Reporting | `[ ]` | | |
| B4 | Quality Assurance and Quality Management of IT | `[ ]` | | |

---

## The six reflexes that answer most Domain 2 questions

1. **Governance directs and holds to account; management executes.** Governance sets objectives,
   approves the risk appetite and monitors. Management plans, builds and runs. When a stem asks who
   should approve or own something at the top of the chain, the answer is the board or a board
   committee, not the CIO.
2. **Alignment to business objectives is the standing test.** An IT strategy, architecture, project
   portfolio or metric that cannot be traced back to what the business is trying to do is the finding,
   even when everything in it is individually sensible.
3. **Accountability cannot be delegated, outsourced or transferred.** You can move an activity to a
   vendor, a cloud provider or an insurer. The answerability stays with your organization.
4. **Ownership is explicit and it is usually the business.** Data, risk, systems and processes each
   need a named owner with the authority to decide. "IT owns it" is the wrong answer far more often
   than it is the right one.
5. **A policy with no supporting standard is unenforceable and untestable.** Trace requirements down
   the hierarchy; the break in the chain is the finding.
6. **Measure outcomes and exposure, not activity.** Tickets closed and projects started are activity.
   Whether the objective was achieved, and whether risk is building, are what governance needs.

---

## Part A — IT Governance

### A1. Laws, Regulations, and Industry Standards  `[ ]`

- You are not expected to be a lawyer, and the exam does not test statute text. **It tests whether a
  process exists** to identify what applies, assign ownership, embed it in policy and controls, and
  monitor for change. That is the answer to most "how would the auditor determine compliance" stems.
- Categories worth recognising: privacy and data protection (GDPR, CCPA/CPRA and similar), sector
  regimes (HIPAA for health data, GLBA for financial institutions, SOX for financial reporting),
  contractual regimes that behave like regulation (**PCI DSS is contractual, not law**, which is a
  distinction stems use), plus breach notification, data residency and cross-border transfer rules.
- **SOX pulls ITGCs into scope** because access, change and operations controls underpin the
  application controls over financial reporting. That is the structural link between this domain and
  Domain 4.
- Conflicting requirements across jurisdictions: legal counsel decides, and the working approach is
  generally to satisfy the most restrictive applicable requirement rather than to average them.
- **Compliance is a business obligation with business owners.** An organization where the compliance
  register lives only with IT has a governance problem, because IT cannot accept legal risk on
  behalf of the enterprise.
- Non-compliance found during an audit is reported through the normal channel — and where it may be
  criminal or reportable, escalated to legal and the audit committee rather than resolved locally.

### A2. Organizational Structure, IT Governance, and IT Strategy  `[ ]`

- **The COBIT split is the mental model**: governance is **evaluate, direct and monitor**; management
  is **plan, build, run and monitor**. Governance belongs to the board. When a stem describes an
  activity, ask which of those verbs it is.
- **IT strategy committee versus IT steering committee** is a favourite item:
  - **Strategy committee** — board level, advises the board on IT direction, investment and alignment.
  - **Steering committee** — management level, prioritizes projects, allocates resources, monitors
    delivery.
  Confusing which one is board-level is exactly the error the distractors are built on.
- **Reporting lines carry control meaning.** A CISO reporting to the CIO creates a conflict, because
  the CIO is measured on delivery and availability while the CISO may need to delay or block. An
  internal audit function reporting to the CFO cannot be independent of finance.
- IT strategy must trace to business strategy, be approved at the right level, be funded and
  resourced, and be reviewed on a cycle. A strategy document with no portfolio behind it is a wish.
- **Balanced scorecard for IT**: financial, customer, internal process, and learning and growth.
  The point is that a purely financial view of IT misses everything that determines next year.
- Structures: centralized (consistency, less local fit), decentralized (fit, duplication and
  inconsistent control), federated (shared core with local delivery). Each carries a different
  control profile, and none is the "right" answer without the business context.
- Segregation of duties at the organizational level: development separate from operations, security
  administration separate from security monitoring, and nobody able to both authorize and execute.

### A3. IT Policies, Standards, Procedures and Practices  `[ ]`

- **The hierarchy, which the exam tests directly:**
  - **Policy** — mandatory statement of management intent, broad and stable.
  - **Standard** — mandatory specifics that make the policy testable: which algorithm, what key
    length, which configuration.
  - **Procedure** — the step-by-step how-to.
  - **Guideline** — advisory, discretionary.
  - **Baseline** — the minimum configuration a class of system must meet.
- **A policy with no standard beneath it cannot be enforced or tested.** "Data shall be protected
  appropriately" is not auditable. Tracing from a policy statement down to the standard, the
  procedure and then the evidence is the standard audit path in this topic.
- Lifecycle: drafted, approved at the right level, communicated, acknowledged, and **reviewed
  periodically and on significant change**. A policy last reviewed six years ago describes an
  organization that no longer exists.
- **Exceptions need an owner, a documented risk acceptance by someone with authority, a compensating
  control, and an expiry date with re-approval.** A standing exception with no end date is not an
  exception; it is evidence the policy is wrong and should be changed.
- Evidence of enforcement matters more than evidence of existence. Acknowledgement statistics,
  exception volumes, and instances of the policy actually being applied are what you test.

### A4. Enterprise Architecture and Considerations  `[ ]`

- EA describes how business capability, information, applications and technology fit together, and
  where they are going. Layers: **business → information/data → application → technology.**
- What it is *for*, from an audit seat: reducing duplication, controlling technical debt, making
  dependencies visible before something breaks, and ensuring new solutions fit a deliberate target
  state instead of accumulating.
- Governance mechanisms: an architecture review board, a documented target state and roadmap, and an
  exception process for solutions that deviate.
- Recurring findings: no maintained current-state inventory (so nobody knows what depends on what),
  a target state written once and never updated, and **solutions procured or built outside
  architecture review** — which overlaps directly with shadow IT in Domain 4.
- End-of-life and end-of-support technology is an architecture risk with a compliance edge: unsupported
  software cannot be patched, which quietly invalidates the vulnerability management programme.
- Cloud and integration decisions belong here too — data residency, portability, and whether the
  architecture has created lock-in that nobody evaluated.

### A5. Enterprise Risk Management  `[ ]`

- The cycle: **identify → assess (likelihood and impact) → respond → monitor → report.** Risk that is
  identified and never revisited is a list, not a programme.
- **Four responses: avoid, mitigate, transfer/share, accept.** Note what transfer does and does not
  do — insurance and outsourcing move financial consequence, **not accountability**, and never the
  regulatory obligation.
- **Appetite, tolerance and capacity** are three different things and stems exploit it:
  - **Appetite** — how much risk the organization is *willing* to take pursuing its objectives.
  - **Tolerance** — the acceptable variation around that, in practice.
  - **Capacity** — the maximum it could absorb before it fails.
  Appetite should sit below capacity, and an appetite set at or above capacity is a governance finding.
- **Risk acceptance requires authority proportionate to the risk.** The business owner accepts
  business risk; above a threshold it goes to the board. **IT accepting a business risk on the
  business's behalf is a finding** even when IT is the only party paying attention.
- Risk register contents: description, owner, inherent rating, controls, residual rating, response,
  action and status. Residual risk above appetite with no action is the thing to look for.
- **Aggregation**: many individually acceptable risks in the same area can collectively exceed
  appetite. Registers that only ever look at rows one at a time miss this.
- **Three lines model**: first line owns and manages risk in the business, second line (risk,
  compliance, security) sets frameworks and oversees, third line (internal audit) provides independent
  assurance. **Internal audit must not own, design or operate controls** — doing so consumes the
  independence that makes the third line worth having.

### A6. Privacy Program and Principles  `[ ]`

- Core principles that recur regardless of regime: lawful basis and transparency, **purpose
  limitation**, **data minimization**, accuracy, storage limitation, integrity and confidentiality,
  and accountability.
- **Controller versus processor**: the **controller determines the purposes and means** of processing
  and carries primary accountability. The **processor acts on the controller's documented
  instructions**. Both have obligations; the accountability does not move.
- **Privacy is not a subset of security.** Security asks whether the data is protected. Privacy also
  asks whether you should be collecting, keeping and using it at all. **A perfectly secured database
  of data you had no basis to collect is a privacy failure and a security success simultaneously** —
  and stems are built on exactly that gap.
- **Privacy by design and by default**, which in practice means the **privacy impact assessment
  happens before the processing starts**, not after go-live. A DPIA produced to document a system
  already in production has been used as paperwork rather than as a control.
- Consent, where it is the basis relied on, must be freely given, specific, informed, unambiguous and
  as easy to withdraw as to give. Pre-ticked boxes and consent bundled with terms of service fail.
- Data subject rights: access, rectification, erasure, portability, restriction and objection. The
  audit question is whether there is a process that can actually find all of someone's data in time —
  which depends on the data inventory being real.
- Cross-border transfers need a lawful mechanism; breach notification has defined clocks. Know that
  the obligation and the timer exist rather than memorising each jurisdiction's number.
- **Test data is the classic crossover finding**: production personal data copied into a development
  environment carries every obligation with it, and usually none of the controls. Mask or synthesize.

### A7. Data Governance and Classification  `[ ]`

- **The roles, which the exam tests hard:**
  - **Owner** — a business role. Decides classification, approves access, accepts residual risk.
  - **Custodian** — usually IT. Stores, protects, backs up and administers according to the owner's
    decisions.
  - **Steward** — day-to-day quality, definitions, lineage and standards for the data.
  - **User** — uses it within the terms granted.
- **Classification is the owner's decision, not IT's**, and access approval is the owner's too. When
  a stem has IT deciding sensitivity or granting access on its own authority, that is the finding.
- The classification scheme should have few enough levels that people actually apply them, and each
  level must map to concrete handling requirements — labelling, encryption, transmission, retention,
  access, and disposal. **A scheme with no handling requirements attached is decoration.**
- Data quality dimensions worth naming: accuracy, completeness, consistency, timeliness, validity,
  uniqueness.
- **Lifecycle**: create → store → use → share → archive → destroy. Retention driven by legal,
  regulatory and business need. **Over-retention is a risk, not caution** — it enlarges every breach
  and can itself breach storage limitation obligations.
- Authoritative source designation, master data management and lineage: when two systems disagree,
  governance is what says which one is right.
- Classification and ownership are the prerequisites for most of Domain 5. You cannot protect data
  proportionately until someone has said what it is worth.

---

## Part B — IT Management

### B1. IT Resource Management  `[ ]`

- People: skills inventory against the portfolio's needs, succession planning, **key-person
  dependency**, cross-training, and documented procedures someone other than the author can follow.
  The single-threaded expert is a resilience finding as much as an HR one.
- Financial management: budgeting, forecasting, and how costs reach the business.
  **Chargeback** allocates cost to consumers and changes their behaviour; **allocation** spreads cost
  without a demand signal; **showback** informs without billing. If a stem is about controlling
  demand, chargeback is the mechanism.
- Sourcing strategy — in-house, outsourced, offshore, hybrid — is a resource decision with a control
  profile attached, and it should follow from strategy rather than from a single procurement.
- Capacity of the *team* is as real as capacity of the infrastructure; a portfolio approved without
  reference to delivery capacity produces the late projects nobody can explain.
- Audit angle: does resourcing trace to the approved portfolio, are critical roles covered, and is
  training a line item that survives budget pressure.

### B2. IT Vendor Management  `[ ]`

- Lifecycle: **need and strategy → due diligence → selection → contract → onboarding → ongoing
  monitoring → exit.** Evaluation criteria are set **before** proposals arrive; criteria written
  after the responses are in are criteria fitted to a preferred answer.
- Due diligence proportionate to criticality and data sensitivity: financial viability, security
  posture, certifications and their scope, **subcontractors (fourth-party risk)**, insurance,
  references, and geography.
- Contract essentials to recognise: service levels and remedies, security and privacy requirements,
  **right to audit**, breach notification obligations and timescales, data ownership and return,
  consent required before subcontracting, liability, and **exit and transition assistance**. The exit
  clause is the one organizations discover they need at the worst possible moment.
- **Ongoing monitoring is where vendor programmes actually fail** — thorough due diligence at
  onboarding, then nothing for five years while the vendor's business, subcontractors and security
  posture all change. Reassess on a risk-based cycle and on trigger events.
- Assurance reports: check the period, the scope, the exceptions, whether subservice organizations
  were carved out, and the **complementary user entity controls** you are responsible for (Domain 1, A2).
- **Accountability stays with the organization.** The regulator and the customer are not interested
  in which supplier failed. This is the reflex that answers most cloud and outsourcing stems.
- Concentration risk: several critical services with one provider, or several providers on one
  underlying platform, reintroduces the single point of failure at the commercial layer.

### B3. IT Performance Monitoring and Reporting  `[ ]`

- **KPI versus KRI**, and this is the item to get right: a **KPI** measures how well an objective *is
  being achieved* and looks backward at outcomes. A **KRI** is a **forward-looking** signal that
  exposure is building **before** the loss occurs. A KRI that only moves after the incident is a KPI
  wearing the wrong label.
- Good metrics are few, owned, tied to an objective, and drive a decision. **Activity metrics flatter
  and explain nothing** — tickets closed, projects initiated, scans run.
- **Question who produces the number and whether they can influence it.** Self-reported performance
  by the team being measured, with no independent verification, is the recurring finding here and in
  vendor management.
- Thresholds and escalation criteria are agreed in advance. A metric with no defined "what happens
  when it goes red" produces reporting rather than management.
- Benchmarking and maturity models: **a maturity assessment describes capability; an audit concludes
  on control effectiveness.** They are not substitutes, and a high maturity rating is not an audit
  opinion.
- Reporting cadence and audience: the board needs exposure and trend, management needs operational
  detail. Sending the same pack to both means one of them is not being served.

### B4. Quality Assurance and Quality Management of IT  `[ ]`

- **QA versus QC**: **QA works on the process to prevent defects**; **QC inspects the deliverable to
  detect them**. Preventive versus detective, one level up. Stems describe an activity and offer both
  labels.
- A quality management system covers standards, methods, reviews, defect tracking and improvement.
  Evidence of it operating is defect trend data that someone acts on, not the manual describing it.
- **Independence of QA from delivery is the structural control.** A QA function reporting to the
  project manager whose deadline it may threaten will find fewer things, later. Where that structure
  is unavoidable, the compensating control is a reporting line for quality issues that bypasses the
  project.
- Peer review, walkthroughs and inspections are QC activities with different rigour; inspection with
  defined roles and entry criteria is the most formal.
- **Root cause analysis of recurring defects** is what converts quality control into quality
  assurance. Fixing the same class of defect repeatedly without changing the process is QC forever.
- Lessons learned must land somewhere the next project reads. A lessons log nobody consults is the
  quality equivalent of the unreviewed log in Domain 4.

---

## The six confusions this domain turns on

| Pair | The discriminator in one line |
|---|---|
| Policy / standard / procedure / guideline | Mandatory intent / mandatory specifics / how-to steps / advisory. |
| Owner vs custodian vs steward | Business decides / IT stores and protects / day-to-day quality and definitions. |
| Appetite vs tolerance vs capacity | Willing to take / acceptable variation / maximum survivable. |
| QA vs QC | Process, preventive / deliverable, detective. |
| KPI vs KRI | Backward at achievement / forward at exposure building. |
| Controller vs processor | Determines purposes and means / acts on instruction — accountability does not move. |

Drill them directly: `python drill.py game coldread --domain 2`, or
`python drill.py drill --topic "Enterprise Risk Management" -n 8`.

---

## Sources

- ISACA, *CISA Exam Content Outline* — <https://www.isaca.org/credentialing/cisa/cisa-exam-content-outline> (domain weight, section and topic structure, exam length; verified 2026-07-30)

All explanatory content above is original. No ISACA question, review-manual text or other
third-party exam material is reproduced here.
