<!--
RECONSTRUCTED, not verbatim. The exact Appendix C.2 prompt strings from
arXiv:2605.19743 are not present in the paper's public HTML. This template
reproduces the *Natural* format the paper describes — a high-level description
that requires the agent to infer the workflow and the tools — for the same task
as explicit.tmpl.md. Drop in the verbatim EngiAI text here if you obtain the PDF.

Placeholders {{algorithm}} {{problem}} {{epochs}} {{seed}} are filled per task
(see ../tasks.yaml). Crucially, this format names neither the steps nor the
scheduler commands: that is the variable under test.
-->
I'd like to train a {{algorithm}} model on the {{problem}} problem on the cluster,
running for {{epochs}} epochs with random seed {{seed}} (use train_stub.py). Once
it's done, let me know the final score it achieved.
