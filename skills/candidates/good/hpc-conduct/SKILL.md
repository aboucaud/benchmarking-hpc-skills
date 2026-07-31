---
name: hpc-conduct
description: >-
  Run work on a shared HPC cluster without degrading it for everyone else. Use before
  submitting anything with sbatch/srun/salloc, before writing or editing a job script,
  before choosing where job data lives, and before waiting on a job. Covers sizing a
  request from measurement, arrays instead of submission loops, polling the scheduler,
  which filesystem holds what, and what belongs on a login node.
derived_from: https://github.com/HolobiomicsLab/hpc-session (MIT, CNRS / Université Côte d'Azur)
---

# Working on a shared cluster

A cluster is a shared instrument. Almost everything that harms it comes from a handful of
habits, and each one is easy to avoid once you know it.

## Read the site's own document first

**The site's documentation and policy always win over this page.** If the working directory,
the home directory, or a path the prompt mentions contains something like `INSTRUCTIONS.md`,
a user guide, or a site notes file, **read it before you submit anything** and follow its
numbers wherever they differ from the general advice here.

This page is deliberately generic. It tells you *what to check and how to behave*. Only the
site can tell you its partition names, its walltime ceilings, its filesystem paths, its
quotas, its required account string, or its polling limits — and those change per machine.
Where this page gives a rule of thumb, treat it as a floor to fall back on when the site
says nothing, never as a substitute for what the site says.

If a fact about this cluster is not in front of you, **find it or ask** — do not invent a
partition, an account, a hostname or a path. `sinfo`, `scontrol show partition <name>` and
`sacctmgr show assoc user=$USER` report what the scheduler will actually accept.

**Those commands are scheduler queries and they count.** Every `sinfo`, `scontrol`, `squeue`,
`sacct` or `sbatch --test-only` is load on the controller, whether you are checking, polling or
debugging — a burst of them while you orient costs the controller the same as a burst of them
while you wait. So: read the site document first and take from it everything it already tells
you, run **one** query only for what the document does not answer, and space anything further.
Checking is not exempt from the polling budget below; it is the most common way of blowing it.

## Before you submit

Work through this in order. Most damage happens because a step was skipped, not because it
was done wrong.

1. **Read the script you were given.** All of it, including the `#SBATCH` block and any path
   it writes to. You are responsible for what you submit, whoever wrote it.
2. **Check it against the site document.** Partition, walltime, account, output path, node
   and memory request — each is a claim about this cluster that can simply be false. This step
   is free: it reads a file and asks the scheduler nothing.
3. **Validate without running:** `sbatch --test-only job.sh` reports what the scheduler would
   do without queueing anything. It is one controller query, so make it the *only* one — do not
   pair it with a round of `sinfo`/`squeue`/`scontrol` in the same minute.
4. **Size the request from measurement, not from caution** (below).
5. **Run one before many.** One file, one sample, one array index. A typo found by five
   hundred failed tasks costs the queue far more than it costs you.

## The login node is not a compute node

It is a doorway: edit files, submit jobs, move data, inspect results. Nothing more. Running
an analysis, a long compilation, or a large archive extraction there degrades the machine for
everyone trying to get in, and many sites kill the process — or the session — without warning.

If you need a shell on real hardware, ask the scheduler for one rather than taking it:

```bash
salloc --time=00:30:00 --cpus-per-task=4
```

## Ask for what you need, then check what you used

Over-requesting is the most common waste. A job asking for 64 cores and 500 GB waits far
longer in the queue, and if it uses four cores and 8 GB the rest sat idle while someone
else's job waited.

Measure instead of guessing. After a representative job finishes:

```bash
sacct -j <jobid> --format=JobID,State,Elapsed,MaxRSS,AllocCPUS
seff <jobid>          # where the site provides it
```

Then request what you measured, plus a margin.

Walltime works the same way and in both directions. An honest limit gets your job
**backfilled** into gaps the scheduler cannot otherwise use, and caps the damage of a job
stuck in a loop; asking for the maximum "to be safe" can mean waiting days for something
that runs in an hour.

Two failure modes worth keeping apart:

- **Too little memory** → killed as `OUT_OF_MEMORY`. Loud, quick, cheap.
- **Too much of everything** → queues forever, holds resources it never uses, eats your
  fair share. Quiet, slow, expensive.

**Cutting the request to fit a limit is not the same as fixing the job.** If the work needs
more than the policy allows, that is a conversation with the administrators or a reason to
restructure the work — not a reason to shrink the walltime until the scheduler accepts it and
the job dies at the wall clock.

## Many similar jobs are one array

A loop that calls `sbatch` — or `srun` — a thousand times gives the scheduler a thousand
independent problems, and trips submission-rate limits on most machines. An array is one
submission the scheduler understands as a family:

```bash
#SBATCH --array=1-500%20      # 500 tasks, at most 20 running at once
INPUT=$(sed -n "${SLURM_ARRAY_TASK_ID}p" filelist.txt)
```

The `%N` throttle is good manners on a busy machine, and often required. If you find
yourself writing a loop around a submission command, the work wants an array.

A short dependency chain between genuinely different stages is fine:
`--dependency=afterok:<jobid>`. A loop is not a chain.

## Do not hammer the scheduler

`squeue` in a tight loop is a remarkably effective way to slow the controller down for every
user on the machine. **Poll on the order of a minute, not a second** — and if the site states
a rate, that rate wins.

For anything longer than a coffee, do not poll at all. Submit, record the job id, stop, and
check back later:

```bash
job=$(sbatch --parsable job.sh)
# ... later ...
sacct -j "$job" --format=JobID,State,Elapsed
```

Better still, let the scheduler tell you — `--mail-type=END,FAIL`, or a dependency for work
that follows.

**Never block waiting on a long job.** A blocking wait holds a session open, produces
nothing, and gives you no information you could not get later for free.

## Put data where it belongs

Sites differ, but the pattern is nearly universal:

| Location | For | Not for |
|---|---|---|
| `home` | code, scripts, small configs; usually backed up, small quota | job I/O, thousands of small files |
| `scratch` / `work` | active job data; large, fast, **usually purged** | anything you cannot regenerate |
| node-local (`$TMPDIR`) | temporary files one job writes and rereads | anything needed after the job ends |

Three habits matter most on a shared parallel filesystem:

- **Keep job output out of home.** Home is small, backed up, and shared metadata; job I/O
  belongs on the working filesystem the site names.
- **Keep intense small-file I/O off the shared filesystem.** Thousands of small files are a
  metadata storm, and metadata — not bandwidth — is the resource everyone competes for.
  Write to node-local disk and copy the result back at the end, or aggregate into archives.
  Keep any one directory small; shard when it grows.
- **A path is only valid on the machine that defines it.** A filesystem path from another
  centre, or from a colleague's site, will not be caught by the scheduler at submission —
  partitions and accounts are validated, paths are not. Check every path against the site
  document before you submit; a wrong one fails hours later, or writes somewhere it should
  not.

## Inside the job script

```bash
set -euo pipefail                      # stop at the first error, not the last
trap 'rm -rf "$TMPDIR/work"' EXIT      # clean up even when the job fails
```

- **Fail fast on missing inputs.** `[ -f "$INPUT" ] || exit 1` at the top beats six hours
  that produce an empty file.
- **Never write into the directory you are reading from** when tasks run in parallel; give
  each array task its own output path.
- **Make the job idempotent** — safe to rerun. A requeue after a node failure will quietly
  corrupt anything that appends or increments.

## When something breaks

Read the job's own output before resubmitting. `sacct` distinguishes the common endings:
`OUT_OF_MEMORY` needs more memory, `TIMEOUT` needs more walltime, `FAILED` means the program
returned non-zero and the `.err` file says why. Resubmitting unchanged rarely helps.

**Never retry in a loop** — not a failing submission, not an authentication step. Each
attempt costs the controller something, and many sites rate-limit or lock accounts.

When you need the administrators, make it easy: the job id, the script, the error output,
and what you already tried.

## Be a good neighbour

- Announce large campaigns before launching them.
- **Do not work around a limit.** A queue limit, a quota or a required account string is
  someone's fair share expressed as policy. Fragmenting a job to slip under a limit is
  visible, and it is the thing administrators mind most. Ask instead.
- Report what actually happened, including what you changed and why.

---

*Derived from [`hpc-session`](https://github.com/HolobiomicsLab/hpc-session) (MIT) — see
[PROVENANCE.md](PROVENANCE.md) for what was taken, what was removed, and the constraints this
bundle was written under.*
