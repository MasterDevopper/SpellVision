---
title: Spec Coverage Matrix
type: spec
updated: 2026-07-25
---

# Spec Coverage Matrix

| Domain | Product intent | ADR/decision | Detailed contract | Impl | Proof | Gaps |
|--------|----------------|--------------|-------------------|------|-------|------|
| Abstraction promise | Y | ADR-001/002 | partial | Y | Y | guided deps incomplete |
| Simple/Advanced | Y | ADR-003 | Doc 13 | Y | Y | copy polish |
| Job lifecycle | Y | — | JOB_LIFECYCLE | Y | partial | ping SM bug |
| Worker protocol | Y | — | WORKER_PROTOCOL | Y | pytest | expand coverage |
| Image families | Y | Doc 26 | classifiers | Y | Y | license UI |
| Video families | Y | Doc 26 | contracts | Y | mostly | Hunyuan i2v C8; Wan 2.2 i2v |
| Model library | Y | Doc 22 / MM spec | Stage-1 only | partial | inventory | downloads/compat |
| Flows | Y | sprint10 docs | importer | Y | Y | — |
| Chain | Y | design docs | Y | Y | historical | nav/ship |
| Studios | Doc 29 | ADR-005 tension | 11d/29 | partial | varies | ship scope Q5 |
| 3D | Y | deferred | 11b/11c | N | N | whole Phase D |
| Shipping | Y | ADR-005 | Doc 28 stub | N | N | installer/deps |
| Theme | Y | — | Doc 16 / ArcaneGlass | Y | visual QA | default preset C12 |

## Related

[[Acceptance Evidence Ledger]] · [[Open Questions Register]]
