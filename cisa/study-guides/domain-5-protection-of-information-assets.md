# CISA Domain 5 — Protection of Information Assets

**Weight: 26% of the exam** (tied with Domain 4 as the heaviest domain; together they are 52% of the exam).

Structure below follows ISACA's published CISA Exam Content Outline, verified 2026-07-26 at
<https://www.isaca.org/credentialing/cisa/cisa-exam-content-outline>. The 15 topics are ISACA's;
the notes are mine and are written from the auditor's seat rather than the engineer's.

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

### Part A — Information Asset Security and Control

| # | Topic | Status | Last drilled | Accuracy |
|---|-------|--------|--------------|----------|
| A1 | Information Asset Security Frameworks, Standards, and Guidelines | `[ ]` | | |
| A2 | Physical and Environmental Controls | `[ ]` | | |
| A3 | Identity and Access Management | `[ ]` | | |
| A4 | Network and End-Point Security | `[ ]` | | |
| A5 | Data Loss Prevention | `[ ]` | | |
| A6 | Data Encryption | `[ ]` | | |
| A7 | Public Key Infrastructure | `[ ]` | | |
| A8 | Cloud and Virtualized Environments | `[ ]` | | |
| A9 | Mobile, Wireless, and Internet-of-Things Devices | `[ ]` | | |

### Part B — Security Event Management

| # | Topic | Status | Last drilled | Accuracy |
|---|-------|--------|--------------|----------|
| B1 | Security Awareness Training and Programs | `[ ]` | | |
| B2 | Information System Attack Methods and Techniques | `[ ]` | | |
| B3 | Security Testing Tools and Techniques | `[ ]` | | |
| B4 | Security Monitoring Tools and Techniques | `[ ]` | | |
| B5 | Security Incident Response Management | `[ ]` | | |
| B6 | Evidence Collection and Forensics | `[ ]` | | |

---

## The five reflexes that answer most Domain 5 questions

Before the topics, internalize these. On a judgment stem, they resolve the answer more often than technical recall does.

1. **Risk assessment precedes control selection.** If an option says "perform a risk assessment"
   or "classify the data" and the stem asks what comes FIRST, it is usually right.
2. **Prevent beats detect; detect beats correct** — *when the stem asks what BEST addresses a weakness*.
   If the stem asks about recovery or evidence, that ranking inverts.
3. **Accountability cannot be outsourced.** Cloud, vendor, managed service — the organization
   still owns the data and answers for it.
4. **Design evidence is not operating evidence.** Policies, approvals and certifications show
   intent. Records of the control actually running, and of exceptions being cleared, show effectiveness.
5. **Completeness is the auditor's instinct.** A sample of what is already managed cannot tell you
   about what was never enrolled. Reconcile to an independent population.

---

## Part A — Information Asset Security and Control

### A1. Information Asset Security Frameworks, Standards, and Guidelines  `[ ]`

- **Document hierarchy** — this is heavily tested. *Policy* = management intent, mandatory, broad
  ("confidential data shall be encrypted"). *Standard* = mandatory specifics (which algorithm, what
  key length). *Procedure* = step-by-step how-to. *Guideline* = recommended, discretionary.
  *Baseline* = the minimum configuration a class of system must meet.
- Common frameworks: ISO/IEC 27001 (the certifiable management system) and 27002 (the control
  guidance), NIST Cybersecurity Framework, NIST SP 800-53, COBIT (governance, mapped to Domain 2),
  CIS Controls, PCI DSS (contractual, prescriptive).
- **Frameworks are inputs, not answers.** Adopting one untailored means the control set reflects the
  author's assumptions, not your risk profile. Tailoring is the expected recommendation.
- Certification (e.g. an ISO 27001 certificate) is third-party, point-in-time, and scoped. Always ask
  what the scope statement actually covered.
- Auditor angle: trace a requirement down the hierarchy. Policy with no supporting standard is
  unenforceable and untestable — that is a finding in itself.

### A2. Physical and Environmental Controls  `[ ]`

- **Layered/defense in depth**: perimeter → building → floor → room → rack → device. Expect stems
  where the weakness sits at one layer and the right answer strengthens that same layer.
- **Tailgating / piggybacking**: the answer is almost always the mantrap (interlocking door) or
  turnstile — a control that physically enforces one authenticated person per entry. Cameras and
  signage are detective or advisory. Note the trap: badge logs cannot detect the person who never badged.
- Environmental: **low humidity → static discharge; high humidity → condensation and corrosion.**
  Target range is roughly 40–60% RH. Know this direction cold, it is a common item.
- Fire: detection (smoke/heat, including under raised floors and above ceilings) vs suppression
  (inert gas or clean agent preferred over water in a data center; wet pipe vs dry pipe vs pre-action).
  **An untested suppression system is the finding**, not the choice of agent.
- Power: UPS bridges the gap; generator carries the long haul. The audit question is almost always
  **regular full-load testing**, because generators that pass unloaded runs fail under real load.
- Also in scope: cable management, water detection under floors, HVAC redundancy, secure media
  storage and disposal, and visitor logging with escort requirements.

### A3. Identity and Access Management  `[ ]`

- **Identification → authentication → authorization → accountability.** Keep them straight; stems
  exploit the confusion.
- Authentication factors: knowledge (password, PIN, security questions), possession (token, smart
  card, phone), inherence (biometric). **Multifactor requires factors of different types.** Password
  + security questions is single-factor. Two biometrics is multimodal, not multifactor.
- Biometrics: false acceptance rate (FAR, security risk) vs false rejection rate (FRR, usability),
  crossover error rate (CER/EER) is the balance point and the usual measure of overall accuracy.
  Lower CER = better device.
- **Least privilege, need to know, segregation of duties.** SoD conflicts in IAM: whoever can reset
  a credential can effectively use the account, so reset rights over privileged accounts are as
  sensitive as the accounts themselves.
- Access lifecycle: provisioning (authorized by the data owner, not IT), modification — watch
  **privilege creep on transfer**, since role changes that add without removing are a classic finding —
  and deprovisioning. Orphan accounts point to a broken HR-to-IT trigger, which is the root cause to chase.
- **Access reviews / recertification**: the effectiveness evidence is that flagged access was actually
  revoked, not that managers signed the attestation.
- Privileged access management: vaulting, checkout, session recording, break-glass accounts with
  after-the-fact review.
- SSO: convenience and reduced password reuse, at the cost of concentrated risk — one credential
  compromise reaches everything, so the SSO credential needs the strongest authentication.
  Federation concepts: SAML, OAuth 2.0 (authorization), OpenID Connect (authentication on top of OAuth).
- Models: DAC (owner grants), MAC (label-based, rigid, government), RBAC (by job role — the usual
  enterprise answer), ABAC (attribute and context driven).

### A4. Network and End-Point Security  `[ ]`

- Know the OSI layers well enough to place a control: packet-filtering firewall (3/4), stateful
  inspection (4), application/proxy firewall and WAF (7).
- **Deny by default.** A rule base ending in permit-any-any inverts the firewall's purpose — it now
  blocks only what someone remembered to prohibit.
- **IDS detects, IPS prevents.** Placement is the tell: a sensor on a mirror/SPAN port sees a copy
  after delivery and cannot block. Inline = can drop. Signature-based (known attacks, low false
  positives) vs anomaly/behavior-based (can catch novel attacks, more false positives).
- **Segmentation** is the recurring theme: flat networks let a compromised workstation reach
  high-value servers with no filtering or monitoring chokepoint in between. DMZ, VLANs,
  micro-segmentation, jump hosts for administrative access.
- VPN: IPsec (network layer, site-to-site or full client) vs TLS/SSL VPN (application-oriented,
  clientless). **Split tunneling** is the exam's favorite VPN risk — the endpoint bridges the
  untrusted internet and the internal network while bypassing corporate inspection.
- Endpoint: anti-malware, EDR, host firewall, disk encryption, application allowlisting (stronger
  than blocklisting), configuration hardening and patching.
- **Coverage is the audit question.** Licenses purchased ≠ agents installed. Reconcile the agent
  inventory against an independent asset inventory and chase every exception.
- Zero trust in one line: never trust based on network location, verify explicitly every time,
  assume breach.

### A5. Data Loss Prevention  `[ ]`

- Three deployment points: **network** (traffic in motion), **endpoint** (data in use, including USB
  and clipboard), **storage/discovery** (data at rest). Cloud DLP and CASB extend this to SaaS.
- **Classification comes first.** DLP can only enforce a definition someone has already made. If a
  stem asks what to do FIRST before deploying DLP, the answer is identify and classify the data.
- Detection methods: pattern matching and regular expressions, keyword and dictionary, exact data
  matching against a known source, document fingerprinting, statistical or machine classification.
- Modes: monitor/audit → alert → block/quarantine → encrypt. Organizations usually start in monitor
  mode. **Leaving it there indefinitely means there is no working control at all** — neither preventive
  nor detective — while management believes one exists. That combination is worse than no tool.
- Principal limitation: **encrypted traffic that is not decrypted for inspection is invisible to
  network DLP.** Also: personal cloud accounts, screenshots and photographs of screens, and
  well-intentioned insiders finding workarounds.
- False positives are the operational killer. Untuned rules produce alert volumes nobody reviews,
  which is how a monitored channel becomes an unmonitored one.

### A6. Data Encryption  `[ ]`

- **Symmetric**: one shared key, fast, suited to bulk data. AES is the standard (128/192/256).
  Weakness is key distribution, and the number of keys grows as n(n−1)/2.
- **Asymmetric**: public/private key pair, slow, suited to key exchange, signatures and small
  payloads. RSA, ECC (equivalent strength at much shorter key lengths), Diffie-Hellman (key
  agreement, not encryption).
- **Direction matters and is heavily tested.** Encrypt with the *recipient's public key* →
  confidentiality (only they can open it). Encrypt/sign with the *sender's private key* →
  authentication, integrity and nonrepudiation (only they could have produced it).
- Hybrid is what real systems do: asymmetric to exchange a symmetric session key, symmetric for the
  data. TLS works this way.
- **Hashing** (SHA-256) is one-way, fixed-length, used for integrity. Not encryption — no
  confidentiality, not reversible. Salting defeats rainbow tables.
- **MAC/HMAC vs digital signature**: an HMAC uses a shared secret, so it gives integrity and origin
  authentication *between the two parties* but **no nonrepudiation** — either party could have
  produced it. A digital signature uses the sender's private key and does provide nonrepudiation.
  This distinction is a reliable exam discriminator.
- Data states: at rest, in transit, in use. Encrypting one says nothing about the others.
- **Key management is where implementations actually fail.** Generation, distribution, storage,
  rotation, escrow/recovery, revocation, destruction. Keys stored beside the data they protect —
  or readable by the application account — reduce encryption to protection against bare-media theft.
  HSMs and dedicated key vaults are the expected answer.

### A7. Public Key Infrastructure  `[ ]`

- Components: **Certificate Authority** (issues and signs, binds a public key to a verified
  identity), **Registration Authority** (verifies identity before issuance), certificate repository,
  and revocation infrastructure (**CRL**, a periodically published list, vs **OCSP**, real-time query).
- A certificate is a signed assertion binding identity to public key. X.509 fields worth knowing:
  subject, issuer, validity period, public key, serial number, CA signature.
- **Root CA belongs offline.** Subordinate/issuing CAs handle day-to-day issuance. An online,
  network-connected root is a finding, because its compromise invalidates the entire hierarchy and
  forces reissuance of everything.
- **Revocation checking is separate from expiry checking.** Ordinary validation catches expired
  certificates. Without revocation checking, a certificate belonging to a compromised key or a
  terminated user stays valid until its natural expiry.
- Trust models: hierarchical (most common), cross-certification, bridge CA, web of trust.
- Certificate lifecycle management is a real-world audit area: unmanaged expiry causes outages;
  unmanaged issuance produces certificates nobody can account for.

### A8. Cloud and Virtualized Environments  `[ ]`

- Service models and where the control boundary sits: **IaaS** (customer owns OS upward),
  **PaaS** (customer owns application and data), **SaaS** (customer owns data, configuration and
  access decisions only). Deployment models: public, private, community, hybrid.
- **Shared responsibility**: the split of *tasks* moves with the model; **accountability for the data
  never moves.** The customer remains data owner and answers to regulators regardless of model.
- Getting assurance without site access: an independent service auditor's report (SOC 2 Type II
  covers operating effectiveness over a period; Type I is design at a point in time). Read the
  **complementary user entity controls** — those are the controls the report assumes *you* perform,
  and unimplemented CUECs are a very common real-world gap.
- Contract and governance points: right to audit, data location and residency, breach notification
  timelines, subcontractor disclosure, encryption and key ownership, **exit and data portability**
  (vendor lock-in), and SLA remedies.
- Virtualization risks: **hypervisor compromise exposes every guest on the host** (the one risk truly
  unique to virtualization); VM sprawl; VM escape; dormant VMs missing patches; snapshots containing
  sensitive data outside normal controls; resource contention between guests.
- Containers: shorter-lived, image provenance and registry scanning matter, orchestration
  (Kubernetes) becomes a high-value control plane.

### A9. Mobile, Wireless, and Internet-of-Things Devices  `[ ]`

- Mobile risk is loss and mixing of corporate and personal data. **MDM/UEM** controls: enforced
  passcode, encryption, remote lock and wipe, jailbreak/root detection, app allowlisting.
- **Containerization with selective wipe** is the usual BYOD answer: it protects corporate data
  without erasing the employee's personal content, which is what makes it acceptable enough to
  actually be adopted. BYOD needs an explicit written agreement covering wipe rights and privacy.
- Wireless: WEP (broken), WPA2 (AES-CCMP; Personal uses a pre-shared key, Enterprise uses 802.1X
  with a RADIUS server and individual credentials), WPA3 (SAE, protects against offline dictionary
  attacks).
- **A static pre-shared key known to former employees is the classic wireless finding** — no
  accountability, no individual revocation. WPA2-Enterprise is the recommendation.
- **Hiding the SSID and MAC filtering are not real controls.** Both are trivially defeated; expect
  them as distractors.
- Wireless attacks: rogue access points, evil twin, deauthentication, war driving. Control: regular
  wireless scanning / WIDS for rogue detection.
- IoT: the defining problem is **devices that cannot be patched and ship with hardcoded or default
  credentials**, which removes the normal remediation path. Fall back to compensating controls —
  network segmentation onto isolated VLANs, monitoring, procurement standards that require
  patchability, and inventory (you cannot protect what you do not know exists).

---

## Part B — Security Event Management

### B1. Security Awareness Training and Programs  `[ ]`

- Distinguish **awareness** (broad, continuous, changes behavior) from **training** (skill-specific)
  from **education** (conceptual depth).
- **Measure outcomes, not attendance.** Completion percentages measure participation. Falling
  simulated-phishing click rates plus *rising* reporting rates measure behavior — and the reporting
  metric matters as much as the click metric, because you want people to raise the alarm.
- **Role-based tailoring** is the standard recommendation: finance staff face payment fraud,
  developers face secure coding, administrators face credential theft, executives face whaling.
- Tone at the top and continuous reinforcement through multiple channels beat any single annual
  event. Awareness decays fast.
- Awareness is a **compensating control for what technology cannot prevent**. It is rarely the BEST
  answer when a specific technical or procedural control is available in the options.

### B2. Information System Attack Methods and Techniques  `[ ]`

- Social engineering: phishing, spear phishing, whaling, vishing, smishing, pretexting, baiting,
  quid pro quo, tailgating. Business email compromise exploits authority and urgency. **The control
  is a mandatory verification procedure with no exceptions for seniority** — callback to a number
  already on record, not the one the caller supplies.
- Application attacks: SQL injection (**parameterized queries plus input validation**), cross-site
  scripting (output encoding), CSRF (anti-forgery tokens), buffer overflow, insecure deserialization,
  path traversal. Note that input validation belongs in the application — a port-based firewall
  passes injection straight through on port 443.
- Network attacks: man-in-the-middle, session hijacking, DNS poisoning/spoofing, ARP spoofing,
  DoS and DDoS, amplification.
- Malware: virus, worm (self-propagating), trojan, rootkit (hides at OS/kernel level), keylogger,
  logic bomb, backdoor, botnet, **ransomware**, fileless malware living in memory.
- **Ransomware separates prevention from recovery.** If the stem asks about the ability to *recover*,
  the answer is tested, offline or immutable backups that cannot be reached from the production
  environment — because attackers deliberately target reachable backups first. Anti-malware and
  email filtering are prevention; insurance is financial transfer, not recovery.
- APT characteristics: targeted, patient, well-resourced, persistent, focused on staying undetected.
- Insider threat: malicious, negligent and compromised insiders. Controls are SoD, least privilege,
  monitoring of privileged activity, and mandatory vacation / job rotation.

### B3. Security Testing Tools and Techniques  `[ ]`

- **Vulnerability scan** enumerates known weaknesses (broad, automated, cheap, produces false
  positives) vs **penetration test** which demonstrates exploitability and **chains findings**
  together the way an attacker would. If the stem asks whether weaknesses can be *combined* to reach
  a target, it is a pen test.
- Test perspectives: black box (no knowledge), white box (full knowledge), grey box. Internal vs
  external. Authenticated scans see far more than unauthenticated ones.
- **Written authorization defining scope, timing, permitted techniques and escalation contacts is
  the non-negotiable prerequisite.** Without it the testing is indistinguishable from an attack and
  may be unlawful. This is the most reliable "MOST important before testing" answer.
- Handling results: **validate before remediating.** Prioritize by exploitability and by the business
  impact of the affected asset, not by the scanner's generic severity rating. Mass unplanned patching
  of production carries its own availability risk.
- Related techniques: code review (static/SAST and dynamic/DAST), fuzzing, configuration and
  baseline review, red team vs blue team vs purple team exercises, bug bounty programs.
- Testing is point-in-time. It complements but never replaces continuous monitoring and a working
  patch management process.

### B4. Security Monitoring Tools and Techniques  `[ ]`

- **SIEM** aggregates, normalizes and correlates events across sources; SOAR adds automated response
  playbooks; UEBA baselines normal behavior and flags deviations.
- **Coverage first.** Monitoring can only see what it receives. Critical sources missing — especially
  **domain controllers**, authentication systems, privileged access and key network devices — is the
  finding, because that is precisely where intrusions show up.
- **Log integrity determines evidential value.** Forward logs to a centralized, access-restricted
  server that the administrators of the source systems cannot modify. Administrators reviewing their
  own activity logs is a segregation of duties weakness, not a control.
- Also required: accurate and synchronized time (**NTP**) across all sources, or correlation and
  timelines are worthless.
- **Alert fatigue**: high volume with no tuning means real incidents are missed inside the noise,
  and the organization ends up learning about breaches from third parties. Tuning, risk-based
  prioritization and clear triage procedures are the fix.
- Retention must satisfy legal, regulatory and investigative needs — intrusions are frequently
  discovered months after the fact, so short retention destroys the ability to scope them.
- Detection sources beyond the SIEM: file integrity monitoring, DLP alerts, threat intelligence
  feeds, honeypots, and reports from users and external parties.

### B5. Security Incident Response Management  `[ ]`

- **Phases: preparation → detection and analysis → containment → eradication → recovery →
  post-incident (lessons learned).** Know the order; FIRST/NEXT questions live here.
- **While something is actively spreading, contain first.** Restoring before eradication reinfects
  and destroys evidence; hunting for who is to blame belongs to the later investigation; regulatory
  notification depends on a scope assessment you cannot yet make. Containment stops the loss growing.
- Preparation is where most of the value sits: defined roles, an out-of-band contact tree, tooling,
  and **documented severity and declaration criteria**. Leaving "is this a major incident?" to
  whoever is on call produces inconsistent escalation and missed notification deadlines.
- **Testing beats approval.** A plan exercised with the actual responders — tabletop, simulation,
  full — and updated from the results is the BEST assurance it will work. Approval and distribution
  are design evidence.
- Coordinate with business continuity and disaster recovery (Domain 4), legal, privacy, HR,
  communications and, where relevant, law enforcement.
- Breach notification obligations are jurisdiction-specific and time-bound; know that they exist and
  that they depend on assessing what data was affected.
- Metrics worth knowing: mean time to detect, mean time to respond, mean time to contain, dwell time.

### B6. Evidence Collection and Forensics  `[ ]`

- **Order of volatility** governs collection sequence: CPU registers and cache → memory and running
  processes → network connections and state → temporary files → disk → archived media. Capture
  volatile data before touching anything else.
- **Never reboot or shut down a compromised machine** if evidence matters — memory is lost and
  anti-forensic routines may trigger. Do not run anti-malware over it either: scanning writes to
  disk, alters timestamps, and may quarantine the very artifacts you need.
- Acquire with a **write blocker**, take a **bit-for-bit image** (which captures slack space,
  unallocated space and deleted artifacts that a file copy misses), and **work only on the copy**.
- **Hash at acquisition and re-hash after analysis.** Matching values prove the image is faithful and
  unmodified, and any independent party can reproduce the check. File counts and byte sizes prove nothing.
- **Chain of custody** is the single most important admissibility factor: continuous documented
  control recording every handler, transfer, purpose and timestamp. One unexplained gap can exclude
  the evidence entirely.
- Evidence qualities to know: relevant, reliable, sufficient, and lawfully obtained. Best evidence
  rule favors originals; the forensic image with matching hashes is what stands in for the original.
- The IS auditor's own role: recognize when an engagement has turned into a potential legal matter,
  **stop and escalate to legal and qualified forensic specialists** rather than continuing to poke at
  the system. Preserving the evidence outranks satisfying your own curiosity.

---

## Sources

- ISACA, *CISA Exam Content Outline* — <https://www.isaca.org/credentialing/cisa/cisa-exam-content-outline> (domain weights, section and topic structure, exam length; verified 2026-07-26)
