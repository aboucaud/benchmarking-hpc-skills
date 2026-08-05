"""The skill forge: synthesis and adversarial critique, decoupled from measurement (#48).

Phase A authors job-type skills and argues with them until they survive review. It does not measure
them: no episode runs here, and a bundle that leaves this package is *defensible, not demonstrated*.
That distinction is the point of the decoupling, and every provenance record states it in words.

Two invariants hold across the whole package, both of them answers to #32:

  Nothing here writes to `skills/candidates/`. Bundles are emitted under `results/skillforge/<run>/`
  and reach the skill set only through a separate, human-run promotion step. In #32 an authoring
  agent held `Write` and overwrote the skill under test with an unaudited 222-line draft; had the
  matrix re-run in that window it would have silently benchmarked the draft.

  There is exactly one firewall. The brief handed to the author and the findings handed back both
  pass through it. #32's authors were blind in round one and then received auditors' findings
  verbatim — and the auditors could see the cases. An adversarial reader's output is exactly as
  contaminated as its input.
"""
