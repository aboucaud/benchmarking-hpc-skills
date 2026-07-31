---
title: "Audit — every case"
---

One page per case, each generated from that case's `case.yaml` and the judged episode
records: the injected defect, a flow of what actually happened, the audit figure, and the
detector and judge detail behind every count.

A cell is only as good as three checks: did the *scheduler* do the work, did anything
actually run, and did the seeds agree. Each case page reports all three.

| Case | Family | What is on the page |
|---|---|---|
| [A1-srun-loop](cases/case-A1-srun-loop.md) | A | what the records say happened, arm by arm |
| [A2-poll-storm](cases/case-A2-poll-storm.md) | A | what the records say happened, arm by arm |
| [A3-no-array](cases/case-A3-no-array.md) | A | what the records say happened, arm by arm |
| [B1-small-files](cases/case-B1-small-files.md) | B | what the records say happened, arm by arm |
| [B2-home-output](cases/case-B2-home-output.md) | B | what the records say happened, arm by arm |
| [B3-login-node-compute](cases/case-B3-login-node-compute.md) | B | what the records say happened, arm by arm |
| [C1-over-limit](cases/case-C1-over-limit.md) | C | what the records say happened, arm by arm |
| [C2-over-request](cases/case-C2-over-request.md) | C | what the records say happened, arm by arm |
| [C3-wrong-partition](cases/case-C3-wrong-partition.md) | C | what the records say happened, arm by arm |

The figures are declared ASTRA outputs, so each is embedded exactly once — on its own case
page — and referenced from anywhere else. That is a MySTRA constraint, not a style choice:
a block embed mints a project-wide identifier and embedding one twice collides.
