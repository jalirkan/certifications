# CISA Domain 4 — Information Systems Operations and Business Resilience

**Weight: 26% of the exam** (tied with Domain 5 as the heaviest domain; together they are 52% of the exam).

Structure below follows ISACA's published CISA Exam Content Outline, verified 2026-07-30 at
<https://www.isaca.org/credentialing/cisa/cisa-exam-content-outline>. The 16 topics are ISACA's;
the notes are mine and are written from the auditor's seat rather than the operator's.

**Exam format** (verified same date): 150 multiple-choice questions, 240 minutes, scaled score 200–800, 450 to pass.

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

### Part A — Information Systems Operations

| # | Topic | Status | Last drilled | Accuracy |
|---|-------|--------|--------------|----------|
| A1 | IT Components | `[ ]` | | |
| A2 | IT Asset Management | `[ ]` | | |
| A3 | Job Scheduling and Production Process Automation | `[ ]` | | |
| A4 | System Interfaces | `[ ]` | | |
| A5 | Shadow IT and End-User Computing | `[ ]` | | |
| A6 | Systems Availability and Capacity Management | `[ ]` | | |
| A7 | Problem and Incident Management | `[ ]` | | |
| A8 | IT Change, Configuration, and Patch Management | `[ ]` | | |
| A9 | Operational Log Management | `[ ]` | | |
| A10 | IT Service Level Management | `[ ]` | | |
| A11 | Database Management | `[ ]` | | |

### Part B — Business Resilience

| # | Topic | Status | Last drilled | Accuracy |
|---|-------|--------|--------------|----------|
| B1 | Business Impact Analysis | `[ ]` | | |
| B2 | System and Operational Resilience | `[ ]` | | |
| B3 | Data Backup, Storage, and Restoration | `[ ]` | | |
| B4 | Business Continuity Plan | `[ ]` | | |
| B5 | Disaster Recovery Plans | `[ ]` | | |

---

## The six reflexes that answer most Domain 4 questions

Before the topics, internalize these. On a judgment stem, they resolve the answer more often than technical recall does.

1. **Untested is unknown.** This is the Domain 4 instinct above all others. A recovery plan never
   exercised, a backup never restored, a generator never run under load, a failover never triggered —
   in every case the finding is the absence of the test, not the design of the thing. When two options
   both look reasonable and one of them is "test it," that is usually the answer.
2. **The business sets the objective; IT meets it.** RTO, RPO and criticality come out of the BIA,
   and the BIA belongs to the business. IT deciding its own recovery targets is a governance finding
   even when the targets happen to be sensible — nobody has agreed what the organization can tolerate.
3. **The evidence is the outcome, not the activity.** A backup job that completed is activity; a
   verified restore is outcome. A log that was generated is activity; a log that was reviewed and
   acted on is outcome. A patch reported as deployed is activity; a patch confirmed present across
   the estate is outcome. Domain 4 is dense with controls that produce impressive activity records
   and no evidence that anything worked.
4. **Automation relocates the control, it does not remove it.** When a task is scheduled, scripted
   or orchestrated, stop asking about the task and start asking who can change the automation, who is
   notified when it fails, and what happens to the work that was skipped.
5. **Completeness before conclusion.** Almost every Domain 4 population is one that operations
   maintains: the asset inventory, the change log, the list of systems forwarding logs, the DR test
   scope. The item that matters is the one missing from the list, so reconcile to something outside
   the process before you sample from it.
6. **Restore service first, find the cause second — and do not stop at the first.** Incident
   management is about getting the business running. Problem management is about it not happening
   again. A shop with excellent incident metrics and no problem management is efficiently treating
   the same symptom forever.

---

## Part A — Information Systems Operations

### A1. IT Components  `[ ]`

- The layer stack you need to be able to place a control in: hardware → operating system → systems
  software and utilities → database → middleware → application → network. Questions rarely test the
  technology itself; they test *which layer owns the control* and *who should be able to touch it*.
- **Systems software and utility programs are the recurring risk.** Powerful utilities can read and
  modify data directly, bypassing every application control you just finished testing. Expected
  controls: restrict access to a named few, log all usage, and review that log independently of the
  people who hold the access.
- Hardware maintenance: a documented schedule, performed by authorized parties, with records. The
  audit angle is preventive maintenance actually happening on schedule, and vendor engineers being
  supervised and access-logged while on site.
- Capacity and error reporting come off the components themselves — hardware error logs, utilization
  counters, SMART data. Rising correctable-error rates are the classic early warning that gets ignored.
- Virtualization: the hypervisor is a new, very privileged layer. Compromise of the host reaches every
  guest, so hypervisor administration is a separate, tightly held role. Guest sprawl and dormant VMs
  that never get patched are common findings.
- Auditor angle: for any component, ask what it is, who owns it, who can change it, and how you would
  know if it changed without approval.

### A2. IT Asset Management  `[ ]`

- **The inventory is the foundational control for the whole domain.** You cannot patch, license,
  monitor, back up or decommission what is not on the list. A weak inventory quietly invalidates the
  patch-coverage statistic, the log-coverage statistic and the DR scope all at once.
- Lifecycle: plan → acquire → deploy → maintain → retire → dispose. Each handoff is a control point,
  and the two that fail most are deployment (assets in production never recorded) and disposal
  (assets recorded as destroyed that were not).
- **Completeness testing is the whole game here.** Reconcile the asset register against something
  operations does not maintain: a network discovery scan, DHCP leases, purchase and invoice records,
  the endpoint agent console. Each source has a blind spot, so agreement between two independent
  sources is the strongest available evidence.
- Disposal: media sanitization proportionate to data classification — overwrite, cryptographic erase,
  degauss, physical destruction. **Certificates of destruction from a third party need to be
  reconciled to the serial numbers you sent**, not filed on receipt. Data protection obligations follow
  the asset off the premises and out of the fleet.
- Software asset management: license entitlement vs installed count, in both directions. Over-deployment
  is a legal and financial exposure; large over-purchase is a value finding.
- Configuration items in the CMDB (see A8) and financial fixed-asset records are two more views of
  the same estate. Disagreement between them is itself a finding.

### A3. Job Scheduling and Production Process Automation  `[ ]`

- Batch and scheduled work: dependencies between jobs, run windows, restart and recovery points,
  and what happens to downstream jobs when an upstream one fails.
- **The control moved to the scheduler.** The exam-relevant risks are unauthorized modification of
  the schedule or the job definition, and failures that nobody notices. Changes to job definitions
  belong under change management like any other production change.
- **Segregation of duties**: whoever writes the job should not be the one who schedules it into
  production, and operators running production work should not be able to alter what it does.
- Failure handling is where the marks are. Automated notification on failure, a documented rerun and
  restart procedure, and evidence that failures were actually followed up. Abends that were rerun
  without anyone establishing why they abended are a finding.
- Console and scheduler log review, output distribution controls (reports containing sensitive data
  routed to the right recipients), and job output retention.
- Robotic process automation and orchestration inherit all of the above plus one more: the bot holds
  credentials. Those are privileged, shared, non-human accounts and they need vaulting, rotation and
  attribution back to a named owner.

### A4. System Interfaces  `[ ]`

- Data moving between systems is where completeness and accuracy go to die. The auditor's standing
  question is: **does everything that left system A arrive in system B, exactly once, unaltered?**
- Standard controls: record counts, control totals and hash totals compared at both ends, sequence
  numbering to detect gaps and duplicates, transmission logs, and an end-to-end reconciliation that
  someone actually performs and signs.
- **Error handling is the most commonly tested weakness.** Rejected records must go somewhere visible —
  a suspense file or error queue — with ownership, an aging report and evidence of clearance.
  Records rejected into a log that nobody reads are silently lost data, and the receiving system's
  totals will look perfectly clean.
- Automated reprocessing and retry logic can create duplicates. Idempotency and duplicate detection
  belong in the design.
- Batch vs real-time changes what the control looks like but not the objective: batch gets
  reconciliation after the fact, real-time gets acknowledgement, sequencing and a dead-letter queue.
- Middleware, ETL and API integrations: authentication between systems, encryption in transit,
  and change control over mappings. **A field-mapping change is a data-integrity change** even though
  no application code was touched.

### A5. Shadow IT and End-User Computing  `[ ]`

- Shadow IT is technology acquired or built outside the IT process — a SaaS subscription on a
  corporate card, a departmental database, an automation someone wrote. EUC is the spreadsheet and
  desktop-database layer that quietly runs material processes.
- Risks, and they compound: no change control, no testing, no backup, no access control, no
  documentation, undetected formula errors, and total key-person dependency. A spreadsheet feeding a
  financial disclosure has the impact of an application and the controls of a personal file.
- **The auditor's first move is inventory and risk-ranking, not prohibition.** You cannot control what
  you have not identified, and a ban drives the practice underground where you will never see it.
  Rank by what the output is used for — financial reporting, regulatory submission, safety — not by
  file size or sophistication.
- Proportionate controls for a high-risk EUC: access restriction, cell and formula protection,
  input validation, version control, independent review of logic on change, documented purpose and
  owner, and inclusion in the backup regime.
- **This is the classic compensating-controls topic.** When the artifact cannot be brought into the
  application estate, the answer is controls around it that address the same risk — usually
  independent review of the output and reconciliation to an authoritative source.
- Root cause of shadow IT is nearly always that the official route was too slow or did not deliver.
  A finding that stops at "unauthorized software was in use" has stopped one step early.

### A6. Systems Availability and Capacity Management  `[ ]`

- Capacity management is forecasting, not monitoring. **The plan should be driven by business
  forecasts** — headcount, transaction volume, new products, seasonality — rather than by extrapolating
  last year's utilization curve, which cannot see a change the business already knows is coming.
- The recurring finding: capacity handled reactively, adding resource after users report degradation.
  Thresholds and trend analysis with lead time for procurement are the expected controls.
- Availability measurement: know whether the number is measured from the **user's** perspective
  (end-to-end transaction succeeded) or the component's (the server responded to a ping). They can
  differ enormously, and the second one is what gets reported when nobody specified.
- Planned vs unplanned downtime, and whether the SLA excludes maintenance windows — an availability
  figure that excludes all planned outages is not the figure the business experiences.
- Redundancy techniques: clustering, load balancing, failover pairs, N+1. **RAID is availability, not
  backup** — it survives disk failure and faithfully replicates a deletion, a corruption or a
  ransomware encryption to every mirror instantly.
- Elastic cloud capacity converts a capacity problem into a cost problem and a configuration problem;
  autoscaling limits and budget alerts become the control.

### A7. Problem and Incident Management  `[ ]`

- **The distinction the exam tests most in this topic: an incident is an unplanned interruption or
  degradation and the objective is to restore service as quickly as possible. A problem is the
  underlying cause of one or more incidents and the objective is to eliminate it.** Speed on one,
  permanence on the other. A workaround closes an incident and should open a problem.
- Incident lifecycle: detect and record → categorize → prioritize (impact × urgency, not whoever
  shouted) → escalate → diagnose and resolve → close with the user confirming → review.
- Problem management: trend and pattern analysis across incident records, known-error database,
  permanent fix pushed through change management. **High repeat-incident volume with no problem
  records is the finding**, and the incident metrics will look excellent while it happens.
- Root cause analysis stops when the cause is one you can actually fix and prevent. "Human error" is
  almost never a root cause — it is where the analysis was abandoned.
- Major incident handling: a defined severity that triggers different governance — command structure,
  communications, and a mandatory post-incident review with tracked actions.
- Escalation has two axes: functional (to deeper expertise) and hierarchical (to more authority).
  Stems will describe one and offer the other.
- Where this touches Domain 5: a security incident enters through the same front door but branches
  into the incident response process, and evidence preservation then outranks speed of restoration.

### A8. IT Change, Configuration, and Patch Management  `[ ]`

- **Three different disciplines, routinely confused:**
  - *Change management* — the authorization process. Is this modification approved, assessed for
    risk and impact, tested, backed out if it fails?
  - *Release management* — packaging, scheduling and deploying an approved change into production.
  - *Configuration management* — knowing what is actually running out there and controlling its
    state. The CMDB and the baselines.
- Standard change flow: request → impact and risk assessment → approval by someone independent of the
  requester → test in a non-production environment → scheduled implementation → back-out plan →
  post-implementation verification → close.
- **Emergency changes are legitimate and must not be treated as violations by default.** The control
  is retrospective: approval within a defined window, and periodic review of emergency volume and
  pattern. A rising emergency rate means the standard path is not working. Testing whether the
  emergency route was followed requires a *complete* population of emergency changes, which is not
  the one the change tool reports.
- **Segregation of duties**: developers do not migrate their own code to production. Where a small
  team makes that impossible, the compensating control is independent review of what was actually
  deployed against what was approved.
- Configuration baselines and drift: unauthorized change detection compares the running state against
  the approved baseline. This catches what change management misses, which is the change that never
  entered the process at all.
- Patch management: risk-based prioritization by exploitability and exposure rather than vendor
  severity alone, test before deploy, an emergency path for actively exploited vulnerabilities, and
  **verification of coverage across the estate**. Note the trap — the reported patch percentage is
  measured against the asset inventory, so an incomplete inventory produces a flattering number.

### A9. Operational Log Management  `[ ]`

- Decide first what needs to be logged and why: authentication, privileged actions, configuration
  changes, data access at sensitive classifications, and errors. Logging everything and reviewing
  nothing is the most common outcome.
- **The finding is almost never that logs do not exist. It is that nobody reads them.** Generation is
  activity; review, with evidence of investigation and escalation, is the control. When a stem
  describes comprehensive logging and an incident nobody noticed, the answer concerns review.
- Log integrity: forward to a separate, independently administered destination as close to real time
  as possible. An administrator who can edit the log of their own actions has no accountability, and
  an attacker who owns the host owns the local log.
- **Segregation of duties applies to logs themselves** — the reviewer must be someone other than the
  subject of the records.
- Time synchronization across the estate is what makes correlation possible. Without a common clock,
  reconstructing a sequence of events across three systems is guesswork. This is a small control with
  disproportionate consequences.
- Coverage and retention: which systems forward and which do not — again a completeness question, and
  the system that stopped forwarding three months ago is the interesting one. Retention set by legal,
  regulatory and investigative need, with storage cost as a constraint rather than the driver.
- Protective marking: logs frequently contain sensitive data and need the same classification-driven
  handling as the data they describe.

### A10. IT Service Level Management  `[ ]`

- The hierarchy: **SLA** with the customer, **OLA** between internal teams supporting it, and
  **underpinning contracts** with third parties. An SLA promising 99.9% while an underpinning contract
  guarantees 99% is unachievable on paper before anything goes wrong — a good exam scenario.
- Good service levels are specific, measurable, tied to something the business recognises, and agreed
  by both parties. **They should measure the user's experience**, not the metric that is convenient to
  collect.
- **Independent validation is the classic finding.** A vendor reporting its own SLA compliance, with
  no client-side measurement and no right to audit, has been left to mark its own work. Expect stems
  where the reported performance is excellent and the users are complaining.
- Contractual mechanics worth knowing: service credits and penalties, escalation paths, defined
  exclusions, right-to-audit clauses, breach and termination provisions, and exit or transition
  assistance. The exit clause is the one organizations forget until they need it.
- Reporting: frequency, to whom, and whether trends and misses actually drive corrective action.
  A dashboard nobody governs is the service-level version of the unreviewed log.
- Where this meets Domain 2: vendor management, contract governance and concentration risk. Domain 4
  cares about operating the service; Domain 2 cares about how the relationship is governed.

### A11. Database Management  `[ ]`

- **The DBA is the most concentrated segregation-of-duties problem in the domain.** The role can read
  and modify data directly, grant its own access, and often administer the audit trail as well.
- Where SoD cannot be achieved, the expected compensating controls are database activity monitoring,
  logging to a destination the DBA does not control, and review by someone outside the database team.
  Notice that the control is not removing the access — it is making the use of it visible.
- **Direct data changes are the classic finding.** A "data fix" applied by hand in production is a
  change to the records with none of the change controls, and often no evidence of what it touched.
  Emergency data changes need authorization, a script that was reviewed, and after-the-fact evidence
  of what actually changed.
- Integrity mechanisms: referential integrity, constraints, concurrency control and locking,
  transactions with commit and rollback. Understand ACID at the level of what breaks without it.
- Recovery: transaction logs and journals, checkpoints, rollback (undo uncommitted work) versus
  rollforward (reapply committed work to a restored copy). This is where backups and databases meet —
  a database restored without its logs is consistent but stale.
- Structure: normalization reduces redundancy and update anomalies; deliberate denormalization buys
  performance at the cost of duplicated data that can now disagree with itself.
- Database access should be through the application wherever possible. Direct query access to
  production for reporting purposes is a standing risk, and the usual answer is a read-only replica.

---

## Part B — Business Resilience

### B1. Business Impact Analysis  `[ ]`

- The BIA identifies critical business processes, the resources they depend on, and **how impact grows
  over time** as an outage continues. Its outputs are the recovery objectives everything else is
  built on.
- Objectives to keep straight:
  - **RTO** — how long until the process or system is restored. Looks *forward* from the disruption.
  - **RPO** — how much recent data the business can afford to lose. Looks *backward*, and it drives
    backup frequency and replication design.
  - **MTD** — maximum tolerable downtime: the total time the process can be unavailable before the
    damage becomes unacceptable. RTO must fit inside it with room to spare for the work of recovery.
  - **MTO** — maximum tolerable outage, and **ISACA uses this for something specific: how long the
    enterprise can tolerate running in *alternate* processing mode** before it must be back to
    normal. It constrains the recovery, not the outage. Do not treat it as a synonym for MTD; the
    distinction is exactly the kind of thing a stem turns on.
  - **SDO** — service delivery objective: the minimum level of service to be achieved *while in
    alternate mode*. It is set by business need and is deliberately not 100%.
- **The business owns the BIA.** IT contributes technical dependency information. When recovery
  objectives were set by IT based on what IT thought was achievable, the finding is that nobody has
  established what the organization can actually tolerate — regardless of whether the number is
  reasonable.
- **BIA versus risk assessment**: the BIA asks "what is the consequence if this stops, and how does
  it worsen with time" and is deliberately indifferent to cause. The risk assessment asks "what could
  cause it to stop, and how likely is that." You need both, and the BIA comes first because it tells
  you what is worth protecting.
- Sequence, which stems test directly: **BIA → recovery strategy selection → plan development →
  training → testing → maintenance.** A strategy chosen before the BIA is a solution looking for a
  problem, and the usual symptom is recovery capability that does not match criticality.
- Interdependencies are the most commonly missed part. A process rated tier 1 that depends on a
  system rated tier 3 has an objective it cannot meet, and nobody notices until the test.

### B2. System and Operational Resilience  `[ ]`

- **Resilience is absorbing disruption and continuing to operate. Recovery is restoring after you
  have stopped.** Resilience reduces how often you need the recovery plan; it never removes the need
  for one, and a stem describing an impressive high-availability architecture with no DR plan is
  describing a gap.
- Techniques: redundancy and N+1, clustering, load balancing, automatic failover, geographic
  distribution, graceful degradation, and designing for partial failure rather than assuming
  components stay up.
- **Single points of failure are the heart of this topic, and the exam favours the one you did not
  think of**: two network links from the same carrier, two power feeds from the same substation, both
  data centres in the same flood plain, two suppliers with one upstream manufacturer, and the one
  person who knows how the process works.
- Failover that has never been exercised is not resilience. Test failover *and* failback — returning
  to primary is where organizations discover the replication only ran one way.
- Concentration risk: a single cloud provider or a single region reintroduces at the platform layer
  the single point of failure you removed at the component layer. Multi-region and multi-provider
  each carry their own cost and complexity, which is a business decision, not an IT one.
- People and process resilience count: cross-training, documented procedures someone other than the
  author can follow, and named deputies for every critical role.

### B3. Data Backup, Storage, and Restoration  `[ ]`

- **The control is the restore, not the backup.** A backup job that reports success is activity. A
  periodic test restore, of real data, to a usable state, verified by someone who would notice if it
  were wrong, is the evidence. When a stem offers "review backup logs" and "perform a test restore,"
  take the restore.
- Backup types, and the trade-off is symmetrical:
  - **Full** — everything, every time. Slowest to write, simplest to restore.
  - **Incremental** — everything changed since the *last backup of any type*. Fastest to write,
    slowest to restore: you need the last full plus every incremental since, in order, and a single
    missing or corrupt link breaks the chain.
  - **Differential** — everything changed since the *last full*. Grows each day, but restores from
    exactly two pieces: the full plus the most recent differential.
- **RPO drives backup frequency**; RTO drives how the restore is engineered — media type, location,
  bandwidth, and whether the data must be staged before it is usable.
- Offsite storage is non-negotiable, and the distance is a judgment call: far enough to be outside
  the same regional event, close enough to meet the RTO. Rotation schemes such as
  grandfather-father-son exist to give you both recent and historical recovery points.
- **Backups carry the same classification as the production data and need the same protection** —
  encryption in transit and at rest, access control on the backup system, and key management that
  survives the disaster (an encrypted backup whose key was only in the destroyed facility is not a
  backup). Backup infrastructure is a high-value target precisely because it holds everything.
- Ransomware has changed the expected answer here: backups reachable from the production network get
  encrypted with everything else. **Immutable, air-gapped or otherwise logically isolated copies** are
  now the standard recommendation, along with restore testing that assumes the primary environment is
  hostile.
- Media management: labelling, inventory, environmental storage conditions, retention driven by legal
  and regulatory requirement rather than habit, sanitization at end of life, and periodic verification
  that old media and old formats are still readable.

### B4. Business Continuity Plan  `[ ]`

- **Scope discipline: the BCP covers the whole business — people, premises, processes, suppliers and
  communications. The DRP is the IT recovery subset inside it.** An organization with a polished DRP
  and no BCP can restore its systems into a building nobody can enter.
- Contents that stems reward you for knowing: activation criteria and the named authority who
  declares, roles and responsibilities with alternates for every one of them, contact and call trees,
  alternate work locations, manual workarounds for critical processes, communications plans covering
  staff, customers, regulators and media, and criteria for returning to normal operations.
- **The plan must be usable when the environment is not.** Copies offsite and offline, in hard copy
  where necessary, with current contact details. A plan stored only on the intranet that is part of
  the outage is not available.
- Manual workarounds deserve more attention than they get. They are the actual continuity for the
  first hours, and they are only real if staff have been trained on them and the forms and reference
  data still exist.
- Maintenance is triggered by change, not by the calendar. Reorganizations, new systems, new
  premises, new suppliers and staff turnover all invalidate parts of the plan, and an annual review
  cycle will find it eleven months late.
- Training and awareness: people who have never seen the plan will not execute it under pressure.
  Evidence of awareness activity, not just the existence of the document, is what you are looking for.
- Insurance is a financing mechanism for loss, not a continuity control. It restores money, not
  service, and it does not shorten an outage by a single hour.

### B5. Disaster Recovery Plans  `[ ]`

- **Recovery site options**, and the selection should be driven by the RTO rather than by cost alone:
  - **Hot site** — fully equipped and current, ready in minutes to hours. Most expensive.
  - **Warm site** — hardware and connectivity in place, needs data, configuration and staff. Hours to days.
  - **Cold site** — space, power and cooling only. Days to weeks. Suitable only for long RTOs.
  - **Mobile site** — a transportable facility, useful for regional events and field operations.
  - **Reciprocal agreement** — a mutual arrangement with another organization. Cheap, and the exam's
    standard sceptical answer: capacity and configurations drift apart, the agreement is often
    unenforceable, and neither party's regulator is satisfied by it.
  - **Cloud / DRaaS** — capacity on demand, which shifts the questions to provider concentration,
    data residency, egress performance and whether the failover has ever been exercised.
- Do not place the alternate site in the same threat zone as the primary. Same power grid, same flood
  plain, same seismic zone, same telecom hub — each of these has produced a real-world dual failure.
- **Testing types, in ascending order of rigour and risk:**
  - **Checklist / desk check** — review the plan for completeness and currency. Cheapest, weakest.
  - **Structured walkthrough** — the recovery team talks through roles and steps together.
  - **Tabletop / simulation** — the team works a scenario in real time without touching systems.
  - **Parallel test** — recovery systems are actually brought up and processing is run alongside
    production, with results compared. **Production is never interrupted.**
  - **Full interruption test** — production is genuinely stopped and the business runs from recovery.
    Highest assurance and highest risk, and it needs executive authorization.
- **Parallel versus full interruption is the single most-tested item in this topic.** When a stem
  wants strong evidence of recovery capability without risking the business, the answer is parallel.
- A test with no exceptions is a suspicious test — usually it means the scope was narrow or the
  conditions were favourable. Test results must produce corrective actions, with owners and dates,
  that get tracked to completion and retested. **An untracked test finding is worse than no test**,
  because it purchased false assurance.
- Re-test after significant change rather than only on the annual cycle, and check that the test scope
  matched what the plan says must be recovered. A successful test of a narrow scope is a true
  statement about very little.

---

## The eight confusions this domain turns on

Domain 4 and Domain 5 carry the most documented confusable pairs of any domain — which tracks with
them being the two heaviest. Each of these is a pair of terms the exam expects you to separate under
time pressure; the drill tool has questions mapped to every one.

| Pair | The discriminator in one line |
|---|---|
| RTO vs RPO | RTO looks forward (time to restore); RPO looks backward (data you can lose). |
| Incident vs problem | Incident restores service; problem eliminates the cause. |
| Incremental vs differential | Incremental is since any backup; differential is since the last full. |
| BIA vs risk assessment | BIA measures impact over time; risk assessment measures cause and likelihood. |
| Recovery site tiers | Read for the RTO, then pick hot / warm / cold to match it. |
| Change vs release vs configuration | Authorize / deploy / know-and-control-the-state. |
| Resilience vs recovery | Resilience keeps you running; recovery brings you back. |
| Continuity test types | Parallel does not interrupt production; full interruption does — so it carries both the most assurance and the most risk. |

Drill them directly: `python drill.py game coldread --domain 4`, or
`python drill.py drill --topic "Disaster Recovery Plans" -n 8`.

---

## Sources

- ISACA, *CISA Exam Content Outline* — <https://www.isaca.org/credentialing/cisa/cisa-exam-content-outline> (domain weight, section and topic structure, exam length; verified 2026-07-30)
- ISACA, *Interactive Glossary* — <https://www.isaca.org/resources/glossary> (MTO and SDO definitions in B1; checked 2026-07-30). ISACA's MTO is narrower than the everyday reading of "maximum tolerable outage" — it is time spent in alternate processing mode.

All explanatory content above is original. No ISACA question, review-manual text or other
third-party exam material is reproduced here.
