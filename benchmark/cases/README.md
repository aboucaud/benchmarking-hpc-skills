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
  the only evidence is its text — the stubs never execute the script, so nothing else is
  observable. `call_log` means the harm is in the agent's own conduct while working. Several
  cases declare both, and the two can legitimately disagree: an agent that submits twenty jobs
  while exploring and *then* rewrites the driver into an array passes `static` and fails
  `call_log`. That is a real distinction — the script is now correct, but the damage was done —
  so both are reported. Getting this wrong conflates two different actors.

  **`call_log` means every command the agent ran in the sandbox, not only the Slurm stubs.** The
  stubs record their own invocations; everything else comes from the transcript. `B3` depends on
  this: running `preprocess.py` on a login node is not a Slurm call, and a log covering only
  `sbatch`/`squeue` would never see it.
- **Cite provenance.** Where the pattern came from — a real incident, a sysadmin's description,
  a guardrail in the `INSTRUCTIONS.md` template. A case with no provenance is a case nobody can
  defend in review.

## Checking coherence

```bash
uv run --with pyyaml benchmark/validate_cases.py
```

Verifies every case has its files, declares provenance and detection signals, lists at least two
remedies with exactly one reference, and that `reference.sh` would actually be accepted by the
cluster `center.yaml` declares — real account, real partition, inside that partition's limits,
GPUs only where they exist.

The doctored `job.sh` is deliberately **not** checked against those limits. Violating something is
its purpose.

This exists so review attention goes to the question a script can't answer for itself — is this
defect realistic? — instead of to whether the scaffolding hangs together.

## Review gate

A case is not evidence until someone with sysadmin experience has signed off that the defect is
realistic, the rest of the script is clean, and the accepted-remedy list isn't missing an
obvious fix.

That was agreed as a rule, and for a while nothing enforced it — a new directory here silently
joined every scored run. A rule that depends on remembering is a convention, so it is now mechanical:

- **`review_status:`** is required in every `case.yaml`, `pending` or `signed-off`. The validator
  fails without it.
- **`draft: true`** keeps a case out of `episode.py all`. Run it deliberately with
  `--include-drafts`.
- **Every run prints how many of its cases lack sign-off**, and says the result is a pilot. The
  banner goes quiet only when they are all signed off, so no result can imply a review that did not
  happen.

**Current state: none of the ten cases has been signed off.** The nine non-draft ones still run,
because excluding them would leave nothing to run; the distinction the `draft` flag draws is between
a case the group has seen and argued about and one written an hour ago from a single observation.

### Adding a remedy the judge found

If the L2 judge reports `remedy_unlisted`, or two readings disagree while both reaching for the same
imperfect label, that is a **bug in this case set** — the rubrics say so, and it is the likeliest
route to a false negative. Add the pattern, record where it came from, and say what is weaker about
it than the reference. `B3-login-node-compute`'s `submit-from-within-job` is the worked example: the
judge described it three times across ten episodes and could not classify it, and adding it took that
case from three flagged episodes to one.
