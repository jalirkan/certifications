# CISA Domain 1 — Information Systems Auditing Process

**Weight: 18% of the exam.**

Structure below follows ISACA's published CISA Exam Content Outline, verified 2026-07-30 at
<https://www.isaca.org/credentialing/cisa/cisa-exam-content-outline>. The 10 topics are ISACA's;
the notes are mine.

**Exam format** (verified same date): 150 multiple-choice questions, 240 minutes, scaled score 200–800, 450 to pass.

> **Read this domain first even though it is only 18%.** It is the one that teaches the voice the
> whole exam is written in. Questions in Domains 2 through 5 are answered from the auditor's seat,
> and the habits below — investigate before concluding, weigh the evidence, protect independence —
> decide items that appear to be about encryption or backups.

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

### Part A — Planning

| # | Topic | Status | Last drilled | Accuracy |
|---|-------|--------|--------------|----------|
| A1 | IS Audit Standards, Guidelines, and Codes of Ethics | `[ ]` | | |
| A2 | Types of Audits, Assessments, and Reviews | `[ ]` | | |
| A3 | Risk-Based Audit Planning | `[ ]` | | |
| A4 | Types of Controls and Considerations | `[ ]` | | |

### Part B — Execution

| # | Topic | Status | Last drilled | Accuracy |
|---|-------|--------|--------------|----------|
| B1 | Audit Project Management | `[ ]` | | |
| B2 | Audit Testing and Sampling Methodology | `[ ]` | | |
| B3 | Audit Evidence Collection Techniques | `[ ]` | | |
| B4 | Audit Data Analytics | `[ ]` | | |
| B5 | Reporting and Communication Techniques | `[ ]` | | |
| B6 | Quality Assurance and Improvement of Audit Process | `[ ]` | | |

---

## The six reflexes that answer most Domain 1 questions

1. **Understand before you act.** When a stem hands you an exception, an anomaly or a complaint, the
   first move is almost never to conclude, extend the sample, or report. It is to establish what the
   thing actually is. Everything else depends on the answer, and the options that skip this step are
   usually the plausible-sounding wrong ones.
2. **Independence is not negotiable for efficiency.** If an option saves time by having the auditor
   design the control, accept the auditee's population, or review their own prior work, it is wrong
   no matter how sensible it sounds. Impairments are disclosed, not managed quietly.
3. **Evidence has a hierarchy, and inquiry sits at the bottom.** The auditor's own re-performance and
   direct observation outrank independent third-party confirmation, which outranks anything the
   auditee produced. **Inquiry alone never supports a conclusion** — it points you where to look.
4. **Risk drives scope, sample and effort.** When a planning stem asks what comes FIRST, an option
   about assessing risk is usually correct. Audit effort that is not proportionate to risk is the
   finding, whether it is too little or too much.
5. **Read the verb.** FIRST asks for sequence. BEST asks for effectiveness. MOST asks you to rank.
   GREATEST CONCERN asks for risk. Four defensible answers with one correct one is the normal
   condition of this exam, and the verb is usually what separates them.
6. **The population must be independent of the party being tested.** A sample drawn from a list the
   auditee compiled tells you about the list. Reconcile to something outside the process first.

---

## Part A — Planning

### A1. IS Audit Standards, Guidelines, and Codes of Ethics  `[ ]`

- **ITAF** is ISACA's IT Audit Framework and it separates three things:
  - **Standards — mandatory.** General (ethics, independence, objectivity, competence, due care),
    performance (planning, supervision, evidence, materiality), reporting.
  - **Guidelines — must be considered**, and a departure from one should be reasoned and documented.
    Not optional in the sense of ignorable.
  - **Tools and techniques — informational.** Examples of how, with no obligation attached.
- The distinction between mandatory and considered is a favourite item. "Guidance" does not mean
  "take it or leave it."
- **Audit charter**: approved at the highest level — board or audit committee — and it establishes
  purpose, authority, responsibility and unrestricted right of access. It is what makes the function
  legitimate, and it is approved by the board rather than by management, because management is
  among the parties being audited.
- **Independence has two halves.** *Organizational*: the reporting line runs to the audit committee,
  not to the CIO or CFO whose areas are being examined. *Professional / attitude of mind*: the
  auditor's actual objectivity.
- **Self-review is the classic impairment.** An auditor who designed, implemented or advised on a
  control cannot later provide independent assurance over it. The answer is disclosure to management
  and the audit committee **before** the engagement, and removal from that scope — not extra care.
- Code of Professional Ethics themes worth recognising: support standards, act with due diligence and
  professional care, serve the interests of stakeholders lawfully and honestly, maintain
  confidentiality, maintain competence, and disclose results to appropriate parties.
- **Competence**: if the team lacks the technical skill for the engagement, you obtain specialist
  support or decline. Proceeding anyway breaches due care regardless of how the work turns out.

### A2. Types of Audits, Assessments, and Reviews  `[ ]`

- Types you should be able to distinguish: compliance, financial, operational, **integrated** (IT and
  financial or operational objectives in one engagement), forensic, administrative, and specialised
  reviews such as third-party assurance.
- **Assurance levels differ**: an audit gives reasonable assurance with an opinion; a review gives
  limited assurance; agreed-upon procedures give no opinion at all, only the factual results of
  procedures the client specified. Do not offer conclusions the engagement type does not support.
- **SOC reports** are heavily tested and easy to muddle:
  - **SOC 1** — controls relevant to the user's financial reporting.
  - **SOC 2** — trust services criteria: security, availability, processing integrity,
    confidentiality, privacy. Restricted distribution.
  - **SOC 3** — a public, general-use summary of a SOC 2.
  - **Type I** reports on the *design* of controls at a point in time. **Type II** reports on design
    **and operating effectiveness over a period.** When a stem offers both, Type II is the useful one,
    and a Type I being relied on as evidence of operation is a finding.
- Reading a SOC 2 Type II properly: check the **period covered** (a report ending nine months ago
  says nothing about now), the **scope**, the **exceptions** the auditor noted, whether subservice
  organizations were **carved out or included**, and the **complementary user entity controls**. The
  CUECs are the part everyone skips — the report's conclusions only hold if your own organization
  performs its side, and nobody has tested that for you.
- Internal versus external audit: different objectives and reporting lines. External audit relying on
  internal audit's work must first assess **competence, objectivity and the quality of the work**.

### A3. Risk-Based Audit Planning  `[ ]`

- The chain: define the **audit universe** → assess risk across it → rank → allocate finite resources
  → produce an annual plan → get it **approved by the audit committee** → revisit when the risk
  profile changes. A plan built on rotation or on last year's plan is not risk-based.
- **The four risks, and the one you control:**
  - **Inherent** — risk before any controls are considered.
  - **Control** — risk that controls fail to prevent or detect.
  - **Detection** — risk that *the auditor's own procedures* fail to find what is there.
  - **Residual** — what remains after controls operate.
- **The auditor influences detection risk only.** High inherent and control risk means you must
  accept less detection risk: larger samples, better evidence, more experienced staff, testing closer
  to period end. Stems test this relationship directly.
- **Materiality in IS audit is not only monetary.** Criticality of the process, volume and
  sensitivity of records, regulatory exposure and reputational impact all count. A control weakness
  over a system with no financial value can still be material.
- Engagement scope and objectives flow from the risk assessment, and are agreed before fieldwork.
- **A scope limitation imposed by management is itself a reportable matter.** Escalate; if it is not
  resolved, disclose it in the report and qualify the conclusion. Quietly working around it is the
  wrong answer even when a workaround exists.

### A4. Types of Controls and Considerations  `[ ]`

- **By purpose**: *preventive* stops it happening, *detective* finds it after the fact, *corrective*
  restores the situation, *deterrent* discourages, *directive* instructs. The usual ranking when a
  stem asks what BEST addresses a weakness is preventive first — but if the stem is about recovery,
  investigation or evidence, that ranking inverts.
- **Compensating controls are narrower than people assume.** A compensating control substitutes for a
  control that genuinely *cannot* be implemented, and it must address the same risk to a similar
  degree. "There is another control somewhere in the process" does not qualify.
- **By nature**, and this distinction is worth real marks:
  - **Automated** — performed by the system, consistent, testable once plus the ITGCs around it.
  - **Manual** — performed by a person, variable, needs sampling across the period.
  - **IT-dependent manual** — a human control that relies on a system-generated report, such as a
    manager reviewing an exception listing. **Its reliability depends entirely on the completeness
    and accuracy of that report**, which must be tested separately. A perfectly performed review of
    an incomplete report is a control that does nothing, and auditors miss this constantly.
- **General controls (ITGCs)** — access, change, operations, backup — underpin everything.
  **Application controls** — input validation, processing totals, output reconciliation — sit inside
  a system. **If ITGCs are ineffective, you cannot rely on the application controls they support**,
  because the application could have been changed without authorization. That dependency is the most
  important structural idea in the domain.
- **Design versus operating effectiveness**: a control that would not achieve its objective even if
  performed perfectly has a *design* deficiency. A well-designed control performed inconsistently has
  an *operating* deficiency. Different causes, different remedies, and stems reward telling them apart.
- Control self-assessment: management assesses its own controls with the auditor facilitating. Useful
  for coverage and ownership; it is **not** independent assurance and does not replace audit.

---

## Part B — Execution

### B1. Audit Project Management  `[ ]`

- Engagement planning covers objective, scope, criteria, resources, timing and budget, and it is
  documented before fieldwork rather than reconstructed afterwards.
- **Workpaper standard**: sufficient that an experienced auditor with no previous connection to the
  engagement could re-perform the work and reach the same conclusion. If your papers do not meet
  that, the conclusion is not supported no matter how right it is.
- Workpapers belong to the audit function, are retained per policy, and are confidential.
- **Supervision and review are controls**, not courtesy. Evidence of review is part of the file.
- Budget pressure is the standing threat to quality. Reducing evidence to hit a deadline is a
  standards breach; the correct response is to escalate the resourcing problem or narrow the scope
  explicitly and say so in the report.
- Communicate progress and emerging issues as you go. Findings should never first appear at the
  closing meeting — surprise costs you the auditee's cooperation and usually the accuracy too.

### B2. Audit Testing and Sampling Methodology  `[ ]`

- **Statistical sampling** uses random selection and lets you project results to the population with
  a measurable confidence. **Non-statistical (judgmental)** may find issues efficiently but supports
  no projection. If a stem asks for a conclusion *about the population*, it needs statistical.
- **Attribute sampling** measures a **rate of deviation** — each item either complied or did not.
  This is **compliance testing**. **Variable sampling** measures **monetary value** and belongs to
  **substantive testing**. Mixing these up is the single most common error in this topic.
- **Compliance testing asks whether the control operated. Substantive testing asks whether the data
  is right, regardless of what the controls did.** Compliance results normally determine how much
  substantive work you need — good controls let you do less, not none.
- Specialised methods: **discovery sampling** when even one occurrence matters (fraud, a critical
  breach); **stop-or-go** to limit work when errors are expected to be rare; **monetary unit / PPS
  sampling**, which weights selection toward larger values and therefore cannot tell you much about
  understatement.
- Sample size drivers: higher confidence → larger; higher tolerable error → smaller; higher expected
  error → larger. **Population size has surprisingly little influence** once the population is large,
  which is counter-intuitive and therefore tested.
- **An exception is a question, not a conclusion.** Establish its nature and cause before you
  extrapolate, extend or report. One deviation may be a keying slip, a one-off, or the visible edge of
  a systematic breakdown that occurs whenever some condition holds — and those lead to three
  completely different engagements. (This is the scenario in `python drill.py case d1-one-exception`.)

### B3. Audit Evidence Collection Techniques  `[ ]`

- **The hierarchy decides a lot of questions.** Strongest to weakest, roughly: the auditor's own
  re-performance and direct observation → independent external confirmation → documentation produced
  by an independent party → documentation produced by the auditee → **inquiry of the auditee**.
- **Inquiry alone is never sufficient.** It is excellent for direction and understanding, and it must
  be corroborated by something you did not receive from the person being tested.
- Techniques and what each is actually good for: **inspection** of documents and configurations,
  **observation** (real-time, but people behave differently when watched and it only evidences the
  moment you were there), **re-performance** (strong, because you did it), **recalculation**,
  **confirmation** with third parties, and **analysis** using CAATs.
- Evidence qualities: **sufficient** (enough of it), **reliable** (source and nature), **relevant**
  (bears on the objective), and **useful**. Independence of the source is the main driver of
  reliability, followed by whether it is original rather than a copy.
- **Population integrity comes before sampling.** Reconcile the population to a source the auditee
  does not control — system extracts against independently produced logs, listings against a general
  ledger, records against a third-party feed. The dangerous item is the one that never appeared on
  the list you were handed.
- If evidence may become a legal matter, chain of custody starts immediately and the engagement
  escalates to legal and qualified forensic specialists (see Domain 5, B6).

### B4. Audit Data Analytics  `[ ]`

- **Establish the completeness and accuracy of the data before you analyse it.** Reconcile record
  counts and control totals to the source system. Every conclusion drawn from an extract inherits the
  extract's defects, and an analysis over 100% of the wrong population is worse than a small sample
  of the right one because it looks authoritative.
- CAAT techniques worth telling apart:
  - **Generalized audit software** — query, stratify, join, recalculate, find gaps and duplicates.
  - **Test data** — you submit known inputs and compare to expected outputs. Tests only what you
    thought to test, and the risk is contaminating production if it is not properly isolated.
  - **Parallel simulation** — run real production data through logic you built, compare results.
    Strong evidence about processing over real volume.
  - **Integrated test facility (ITF)** — a dummy entity inside the live system, so you test the real
    production code. Powerful, and the risk is that test transactions contaminate real balances if
    they are not isolated and reversed.
  - **Embedded audit modules / SCARF** — monitoring built into the application to capture items
    meeting audit criteria as they occur. Must be designed in during development, and you are relying
    on code you now need assurance over.
- **Continuous auditing versus continuous monitoring** is a distinction the exam likes:
  **monitoring is management's** activity over its own processes; **auditing is the auditor's**. If
  the auditor builds and runs what is really a management monitoring control, independence is at risk.
- Analytics can shift you from sampling to full-population testing, which changes the conclusion you
  are entitled to draw. It does not remove the need to investigate what the anomalies actually are.
- Visualization and dashboards support the finding; they are not the evidence.

### B5. Reporting and Communication Techniques  `[ ]`

- **Finding structure**: *condition* (what is), *criteria* (what should be), *cause* (why the gap
  exists), *effect* (why it matters, in business terms), *recommendation*. Missing criteria makes it
  an opinion. **Missing cause makes the recommendation a guess** — this is the most common weakness
  in real findings and it is directly tested.
- Effect should be expressed as risk and business consequence, not as a restatement of the condition.
  "Access reviews were not performed" is the condition; the effect is what could happen because of it.
- **Agree the facts before you issue.** The closing meeting exists to correct factual error and hear
  management's response, not to negotiate the conclusion.
- **Management's disagreement does not change the finding.** Include their response and their action
  plan, with a named owner and a date; the auditor's conclusion stands on the evidence. Softening a
  supported finding because it was unpopular is the failure mode this topic is testing for.
- Rating and severity reflect risk, not volume of objection and not how easy it will be to fix.
- Distribution is controlled and goes to those with authority to act — with the audit committee or
  board receiving results, which is the structural reason the reporting line matters.
- **Follow-up is part of the process.** The item closes when remediation has been *verified*, not
  when management asserts it is done. Unverified closure is the quiet way an audit function stops
  being useful.

### B6. Quality Assurance and Improvement of Audit Process  `[ ]`

- A quality assurance and improvement programme has two halves: **internal assessment** — ongoing
  supervision and review plus periodic self-assessment — and **external assessment by a qualified,
  independent assessor.**
- **The "at least once every five years" external cycle is the IIA's requirement**, from its Global
  Internal Audit Standards, rather than something ISACA sets. It is the number CISA material and
  practice both work to, and it is the one to have ready — just do not attribute it to ITAF in your
  own working papers. An external assessment can also be satisfied by a self-assessment with
  independent validation.
- Purpose is twofold: conformance with standards and the charter, and continuous improvement of how
  the function works.
- Frontline quality control is supervision and workpaper review, which is why review evidence belongs
  in the file.
- Useful measures: plan completion, cycle time, finding acceptance and remediation rates, stakeholder
  feedback, repeat findings. **Watch the incentives** — a function measured on findings issued will
  produce more, smaller findings, and one measured on acceptance rate will produce softer ones.
- Repeat findings across engagements are a signal about the organization *and* about whether audit's
  recommendations were addressing cause.
- When an audit misses something later found elsewhere, root cause analysis of the miss belongs in
  the programme, not in the individual's appraisal.

---

## The five confusions this domain turns on

| Pair | The discriminator in one line |
|---|---|
| Inherent / control / detection / residual risk | Before controls / controls fail / **your procedures** fail / what is left. |
| Compliance vs substantive testing | Did the control operate, versus is the data right. |
| Design vs operating deficiency | Would not work even if performed perfectly, versus not performed consistently. |
| Preventive / detective / corrective / compensating | Stops it / finds it / fixes it / substitutes where the real control cannot exist. |
| Attribute vs variable sampling | Rate of deviation (compliance) versus monetary value (substantive). |

Drill them directly: `python drill.py game coldread --domain 1`, or
`python drill.py drill --topic "Audit Testing and Sampling Methodology" -n 8`.

---

## Sources

- ISACA, *CISA Exam Content Outline* — <https://www.isaca.org/credentialing/cisa/cisa-exam-content-outline> (domain weight, section and topic structure, exam length; verified 2026-07-30)
- The Institute of Internal Auditors, *Global Internal Audit Standards* / Standard 1312 on external assessments — <https://www.theiia.org/en/group-services/quality-assurance/quality-services/qaip/> (the five-year external assessment cycle cited in B6; checked 2026-07-30). This is an IIA requirement, not an ISACA one.

All explanatory content above is original. No ISACA question, review-manual text or other
third-party exam material is reproduced here.
