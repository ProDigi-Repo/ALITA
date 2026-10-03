# EU AI Act Assessment

> **Status:** draft for review · Regulation (EU) 2024/1689 as amended by the "Digital Omnibus on AI" (political agreement of May 2026). Check that the Omnibus has been published in the Official Journal before relying on the dates below. Not legal advice.

## Role of the organization

| Question | Assessment |
|---|---|
| Provider of an AI system? | Yes, if ALITA is put into service under the organization's own name, including internal use. The organization builds and operates the system. |
| Deployer? | Yes. The organization uses the system in its own research. |
| Provider of a general-purpose AI (GPAI) model? | No. ALITA uses third-party models through OpenRouter and does not train or place GPAI models on the market. GPAI duties stay with the model providers. |

## Risk classification

| Category | Result | Reasoning |
|---|---|---|
| Prohibited practices (Art. 5) | Not applicable | No manipulation, social scoring, biometric identification or emotion recognition |
| High-risk, Annex III | Not high-risk, as long as the intended use is kept | Research search and summarization is not listed. It **would become relevant** if outputs were used, for example, to assess students or applicants (education, employment) |
| High-risk, Annex I (product safety) | Not applicable | Not a safety component of a regulated product |
| Transparency (Art. 50) | **Applicable** | Users interact directly with an AI system (Art. 50(1)). The system generates synthetic text, and with a real voice feature it would generate synthetic audio (Art. 50(2)) |
| AI literacy (Art. 4) | Applicable | Staff who operate or use the system need sufficient AI literacy |

## Timeline

| Obligation | Applies from |
|---|---|
| Prohibitions (Art. 5), AI literacy (Art. 4) | 2 February 2025 |
| GPAI model obligations (for model providers) | 2 August 2025 |
| Transparency obligations, Art. 50 | **2 August 2026** (unchanged by the Omnibus) |
| Art. 50(2) marking for systems already on the market | grace period until 2 December 2026 (Omnibus) |
| High-risk, Annex III | 2 December 2027 (Omnibus; previously 2 August 2026) |
| High-risk, Annex I | 2 August 2028 (Omnibus; previously 2 August 2027) |

## Measures

| Requirement | Measure in ALITA | Status |
|---|---|---|
| Art. 50(1): inform users that they interact with AI | Notice in both tiles of the Interaction Interface; model name shown under every answer | Implemented (v0.6.0) |
| Art. 50(2): machine-readable marking of AI-generated text/audio | API answers carry `model`, and summaries carry `source: llm`. A visible "AI-generated" label on exported text is still missing. Audio would need marking once the voice feature is real | Partial |
| Art. 4: AI literacy | Short user guidance (limitations, checking sources) | Open: training material and attendance record |
| Keep the intended purpose | Intended and excluded uses in the AI system description | Implemented; review when the use changes |
| GDPR (outside the AI Act) | Person names pseudonymized in cluster labels; key only in the browser or `.env` | Partial: legal basis, record of processing, and a data processing agreement with OpenRouter and the model providers are open |

## Trigger for re-assessment

Repeat this assessment if any of these happen:
- outputs are used to evaluate or rank people;
- the voice feature goes live;
- the system is offered outside the organization;
- personal data other than authors and cited researchers is indexed.
