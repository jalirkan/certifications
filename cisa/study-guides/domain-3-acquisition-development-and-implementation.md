# CISA Domain 3 — Information Systems Acquisition, Development and Implementation

**Weight: 12% of the exam** — the lightest domain, and the one with the best return per hour because
its topic list is short and its confusions are few.

Structure below follows ISACA's published CISA Exam Content Outline, verified 2026-07-30 at
<https://www.isaca.org/credentialing/cisa/cisa-exam-content-outline>. The 8 topics are ISACA's;
the notes are mine.

**Exam format** (verified same date): 150 multiple-choice questions, 240 minutes, scaled score 200–800, 450 to pass.

> Domain 3 is about the window in which controls are cheap. Everything here is a variation on one
> theme: decisions made before a system goes live determine what it will cost to control it for the
> next decade, and the auditor's role is to be present for those decisions without becoming
> responsible for them.

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

### Part A — Information Systems Acquisition and Development

| # | Topic | Status | Last drilled | Accuracy |
|---|-------|--------|--------------|----------|
| A1 | Project Governance and Management | `[ ]` | | |
| A2 | Business Case and Feasibility Analysis | `[ ]` | | |
| A3 | System Development Methodologies | `[ ]` | | |
| A4 | Control Identification and Design | `[ ]` | | |

### Part B — Information Systems Implementation

| # | Topic | Status | Last drilled | Accuracy |
|---|-------|--------|--------------|----------|
| B1 | System Readiness and Implementation Testing | `[ ]` | | |
| B2 | Implementation Configuration and Release Management | `[ ]` | | |
| B3 | System Migration, Infrastructure Deployment, and Data Conversion | `[ ]` | | |
| B4 | Post-implementation Review | `[ ]` | | |

---

## The six reflexes that answer most Domain 3 questions

1. **Controls belong in the requirements.** The earlier a control is specified, the cheaper and
   better it is. When a stem offers "add the control now" versus "specify it in requirements," and
   the project is early, the requirements answer wins. Retrofitting is the finding.
2. **The auditor advises; the auditor never designs, approves or owns.** Participation in a project
   is expected and valuable. Designing the controls you will later audit creates a self-review
   impairment that no amount of care fixes.
3. **The business decides, at every gate.** Sponsor, requirements, user acceptance, go/no-go, and
   benefits — all business decisions. An IT-owned version of any of them is the finding.
4. **The business case is alive.** It is revalidated at each gate, not written once and filed. A
   project whose justification has never been re-tested cannot tell anyone whether finishing it is
   still worth doing.
5. **Building it right is not building the right thing.** Verification and validation are separate
   questions, and a system can pass every verification test while failing the business entirely.
6. **Conversion is reconciled, not trusted.** Counts, totals and exceptions, signed off by the
   business data owner. Confidence in the migration team is not a control.

---

## Part A — Information Systems Acquisition and Development

### A1. Project Governance and Management  `[ ]`

- Roles that stems test: the **sponsor** is a business role owning the funding and the benefits; the
  **steering committee** prioritizes and decides at gates; the **project manager** delivers.
  **A project sponsored by IT with no business owner is the archetypal governance finding** — nobody
  is accountable for whether it was worth doing.
- **Stage gates are controls.** Defined criteria, a documented go/no-go decision, and the authority to
  stop. A project that has never had a gate at which it could have been cancelled has not been
  governed, only monitored.
- The scope, schedule and cost triangle, with change control over scope. Uncontrolled scope change is
  how the approved business case quietly stops describing the project being built.
- Estimation techniques worth recognising: **function point analysis** (sizing from functionality
  rather than lines of code), source lines of code, **three-point / PERT** estimation, Delphi, and
  **critical path** for scheduling. Know what each is for rather than how to compute it.
- Risk and issue management within the project: a risk log with owners, and issues escalated on
  defined criteria rather than when they become unavoidable.
- **The auditor's role during a project** is to advise on controls, review at gates and report — while
  remaining independent enough to audit the result. This boundary is examined directly.
- **Sunk cost is the trap in these stems.** The money already spent is not a reason to continue.
  Cancelling a project whose case no longer holds is a successful governance outcome, and options
  that appeal to investment already made are wrong.

### A2. Business Case and Feasibility Analysis  `[ ]`

- **Feasibility has dimensions**: technical (can it be built), economic (is it worth it),
  operational (will it be used and supportable), schedule (can it be delivered in time to matter),
  and legal/regulatory (are we allowed).
- A business case contains the problem, **the options considered including doing nothing**, total cost
  of ownership (build *and* run, not just the project), benefits with named owners, assumptions and
  risks. Benefits with no owner never materialize and nobody notices.
- **The case is revalidated at each gate.** Costs move, benefits erode, the market changes. A case
  approved at initiation and never revisited is the reason projects finish that should have stopped.
- **Benefits realization is measured after go-live, by the business sponsor, against the original
  case.** That is the entire reason for writing the case down, and it connects directly to B4.
- Appraisal methods and their blind spots: **payback period** ignores everything after payback and
  the time value of money; **ROI** is sensitive to how you define the denominator; **NPV** and **IRR**
  handle timing but depend on assumptions nobody revisits. The audit angle is usually the assumptions,
  not the arithmetic.
- For acquisitions rather than builds: the case should compare buy, build and do-nothing on the same
  basis, including the cost of customization and of the upgrade path.

### A3. System Development Methodologies  `[ ]`

- SDLC phases in the classical sequence: feasibility → requirements → design → development → testing →
  implementation → post-implementation review. Know it as a control framework even where the project
  does not literally follow it.
- Approaches to distinguish: **waterfall** (sequential, documented, feedback arrives late),
  **incremental** and **iterative**, **spiral** (explicitly risk-driven, each loop starts with risk
  analysis), **agile/scrum**, **DevOps**, **prototyping** and **RAD**.
- **Agile does not remove controls; it relocates them.** The control questions become: is the
  definition of done inclusive of security and control requirements, is the product owner genuinely
  authorized to accept on the business's behalf, are automated tests actually gating the pipeline, and
  can you trace a production change back to an approved backlog item. An answer claiming agile
  projects need no change control is always wrong.
- **Prototyping's specific risk** is that the prototype becomes the product — non-functional
  requirements, error handling, security and controls were never specified because the demo worked.
- **DevOps and CI/CD move the control into the pipeline.** Who can approve a merge, who can modify
  the pipeline definition, are quality gates enforcing or advisory, and is there separation between
  the authority to commit code and the authority to deploy it.
- **COTS versus bespoke**: with a package, evaluation criteria are set before proposals arrive, source
  code **escrow** protects against vendor failure, and **customization is the risk** — heavy
  modification breaks the upgrade path and recreates bespoke maintenance costs under a licence.
  Gap analysis between requirements and package capability drives the decision.
- Where the organization is buying, the vendor due diligence in Domain 2 B2 applies in full.

### A4. Control Identification and Design  `[ ]`

- **Application controls by stage:**
  - **Input** — the densest area for exam items: edit and validation checks, format, range,
    reasonableness, **check digit** (catches transposition in identifiers), sequence checks,
    completeness checks, existence/validity against reference data.
  - **Processing** — run-to-run totals, control totals, limit checks, reconciliation between stages.
  - **Output** — reconciliation to input, controlled distribution, retention, and handling of reports
    containing sensitive data.
- **Control requirements go in the requirements document**, are designed, built, tested and traced
  like any other requirement. Controls agreed verbally during design and never written down are not
  built, and nobody discovers it until UAT or later.
- **Requirements traceability matrix**: every requirement — including every control requirement —
  traced through design, build, test case and acceptance. It is what lets you answer "was this control
  actually delivered" without reading the code.
- Manual, automated and **IT-dependent manual** controls again (Domain 1, A4). Designing a control as
  a human review of a system report creates a dependency on that report's completeness that must be
  designed and tested too.
- **Segregation of duties is designed into the role model at the outset.** Retrofitting SoD into a
  live system with established roles is expensive and politically hard, which is why the exam places
  the decision here.
- Audit trail, logging and the ability to reconstruct a transaction are **design requirements**, not
  operational afterthoughts. A system that cannot show who changed what cannot be audited later,
  and by then the cost of adding it is prohibitive.

---

## Part B — Information Systems Implementation

### B1. System Readiness and Implementation Testing  `[ ]`

- **Test levels in sequence**: unit → integration → system → **user acceptance**. Alongside them sit
  the non-functional tests: performance, load, stress, volume, security, and **regression**.
- **Verification versus validation is the distinction to have cold.** **Verification asks whether we
  are building it *right*** — does it meet the specification. **Validation asks whether we built the
  *right thing*** — does it meet the business need. A system can pass every verification test and
  still fail validation, because the specification itself was wrong.
- **UAT belongs to the business.** It is performed by users against business requirements, and their
  **sign-off is the go-live control**. IT performing or signing UAT is a finding, and it is one of the
  most reliably tested points in the domain.
- **Entry and exit criteria per level**, defect severity classification, and an agreed rule for what
  severity of defect is permitted to remain open at go-live. "We'll fix it after launch" without a
  defined threshold is how known defects reach production by default.
- **Regression testing after every fix.** The fix that breaks something previously working is the
  reason the discipline exists.
- **Test environments must resemble production** in configuration and volume, or the results do not
  transfer. Performance testing in a scaled-down environment tells you very little.
- **Test data must not be live personal data unless masked or synthesized.** Copying production into
  a development environment carries every obligation and none of the controls — the crossover with
  Domain 2 privacy and Domain 5 data protection, and the rule that protection follows the data.
- Coverage traced back to requirements: a test pass with no traceability cannot demonstrate that the
  control requirements were tested at all.
- The **go/no-go decision** has defined criteria, is made by the business, and comes with an agreed
  and tested back-out plan.

### B2. Implementation Configuration and Release Management  `[ ]`

- Version control over source and configuration, reproducible builds, **configuration baselines**,
  and release packaging. You should be able to say exactly what version of what is in production.
- **Segregation between development and deployment.** Developers do not migrate their own code to
  production. Where team size makes that impossible, the compensating control is independent review
  of **what was actually deployed against what was approved** — not simply a second person clicking.
- **Environment separation** — development, test, staging, production — with controlled promotion
  between them and no development access to production data.
- Release approval, scheduling, stakeholder communication, and a **back-out plan that has been
  tested** rather than described in a paragraph.
- Emergency fixes follow the same principle as emergency changes in Domain 4: legitimate, permitted,
  and controlled retrospectively with approval inside a defined window plus periodic review of the
  volume and pattern.
- Configuration management connects to the CMDB and to Domain 4's A8. This topic is the
  project-side view; Domain 4 is the steady-state view of the same discipline.

### B3. System Migration, Infrastructure Deployment, and Data Conversion  `[ ]`

- **Changeover strategies, which is the most-tested item in this topic:**
  - **Parallel** — old and new run together and outputs are compared. **Safest**, most expensive, and
    heaviest on staff, who are doing both jobs at once.
  - **Phased** — by module or by location. Contains risk and buys learning, but needs temporary
    interfaces between old and new, which are themselves untested code.
  - **Pilot** — one site or group first, then roll out.
  - **Direct / big-bang cutover** — cheapest and fastest, **riskiest**, and back-out may be
    impractical once conversion has run. Reserved for cases where parallel operation is genuinely
    impossible.
- **Data conversion is where the marks are.** The controls are: **record counts, control totals and
  hash totals reconciled source to target**, field-level validation, exception reports worked to
  zero, and **reconciliation signed off by the business data owner rather than by the migration team.**
- **Cleanse before you convert.** Migrating bad data faster is not an improvement, and the conversion
  is the only realistic opportunity. Decide in advance what happens to records that fail validation —
  rejected records with no owner are silently lost data.
- **Rehearse the cutover, including the back-out**, under realistic conditions and within the real
  time window. A cutover plan that has only been read is Domain 4's untested recovery plan wearing
  different clothes.
- Retain the legacy system read-only for a defined period, and confirm you can still satisfy legal,
  regulatory and audit requests for historical data after it is finally retired.
- **Fallback criteria and the decision authority are agreed before the night of the cutover**, not
  improvised at 3am by whoever is still awake.

### B4. Post-implementation Review  `[ ]`

- **Timing**: after the system has stabilized and been used enough to judge, but soon enough that
  people still remember the decisions. A few months is the usual shape. Too early measures teething
  problems; too late measures nothing anyone can act on.
- **Two distinct questions.** First, **did we get the benefits in the business case** — measured by
  the business sponsor against the original figures, which is the whole reason the case was written
  down. Second, **did the process work** — cost against budget, schedule, quality, and what the next
  project should do differently.
- Also in scope: were the **controls implemented as designed and are they operating**, were open
  defects resolved, and did the system meet its non-functional requirements in real use.
- **Independence matters.** A review run solely by the project team that has an interest in the
  verdict will find that the project succeeded. Someone outside the delivery line should be involved.
- Lessons learned have to land somewhere the next project reads. A lessons log written and filed is
  the project-side twin of the unreviewed log in Domain 4.
- Outcomes are real decisions: remediate, invest further, accept, or in the case where benefits
  clearly will not materialize, retire. **A post-implementation review that cannot recommend
  reversing the decision is a formality**, not a control.

---

## The three confusions this domain turns on

| Pair | The discriminator in one line |
|---|---|
| Changeover strategies | Parallel runs both and compares; phased goes piece by piece; direct cutover is cheapest and riskiest. |
| Change vs release vs configuration | Authorize the change / package and deploy it / know and control what exists. |
| Verification vs validation | Building it right, against the spec / building the right thing, against the need. |

Drill them directly: `python drill.py game coldread --domain 3`, or
`python drill.py drill --topic "System Readiness and Implementation Testing" -n 8`.

---

## Sources

- ISACA, *CISA Exam Content Outline* — <https://www.isaca.org/credentialing/cisa/cisa-exam-content-outline> (domain weight, section and topic structure, exam length; verified 2026-07-30)

All explanatory content above is original. No ISACA question, review-manual text or other
third-party exam material is reproduced here.
