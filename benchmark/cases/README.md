# Misuse cases

One directory per misuse category. Each holds a job script with exactly one deliberately
injected defect, plus everything needed to judge whether an agent caught it.

Methodology: [`docs/mvp-misuse-benchmark.md`](../../docs/mvp-misuse-benchmark.md).

## Files

| File | Purpose | Visible to the agent? |
|---|---|---|
| `job.sh` | the doctored script | **yes** |
| `prompt.md` | the fixed instruction the agent receives | **yes** |
| `assets/` | files `job.sh` refers to, so nothing dangles — contents are copied into the sandbox working directory alongside `job.sh`, not into an `assets/` subdirectory | **yes** |
| `case.yaml` | defect, accepted remedies, detection signals | no |
| `reference.sh` | one correct version — ground truth for the judge | no |
| `rubric.md` | scoring guidance for this case | no |

The harness copies only the visible files into the sandbox. An agent that can read
`rubric.md` is measuring nothing.

## Rules

- **Exactly one defect per case.** Account, partition, walltime and resource request must
  otherwise be correct and consistent with `center.yaml`. If two things are wrong, a failure
  can't be attributed to either.
- **`reference.sh` is *a* correct answer, not *the* correct answer.** List every remedy you'd
  accept in `case.yaml:accepted_remedies`. Judging an agent wrong for picking a different valid
  fix is the most likely way to get a false negative.
- **Declare the detection signal.** `static` means the harm lives in the submitted script and
  the only evidence is its text. `call_log` means the harm is in the agent's own conduct while
  working. Some cases have both. Getting this wrong conflates two different actors.
- **Cite provenance.** Where the pattern came from — a real incident, a sysadmin's description,
  a guardrail in the `INSTRUCTIONS.md` template. A case with no provenance is a case nobody can
  defend in review.

## Review gate

A case is not evidence until someone with sysadmin experience has signed off that the defect is
realistic, the rest of the script is clean, and the accepted-remedy list isn't missing an
obvious fix.
