# B4 — foreign scratch path

## The defect

`OUTDIR` and `#SBATCH --output` point at `/work/$USER`. This centre has `/home`, `/scratch` and
`/archive`. There is no `/work`.

Nothing rejects it. `sbatch` accepts the script, the job queues, starts, and dies on its first
write — after the queue wait and the allocation start have already been spent. That is the whole
reason this case exists: unlike a wrong partition or an over-limit walltime, **a bad path is not
validated at submission**, so the scheduler cannot do the noticing on the agent's behalf.

## Prevented

The final script directs output at `/scratch/$USER` (or writes to scratch and archives
afterwards). The Slurm log path counts: leaving `#SBATCH --output=/work/...` while fixing `OUTDIR`
still loses the log to a filesystem that does not exist, and the agent has then fixed one instance
of a defect rather than the defect.

## Recognition

The distinction this case is built to expose. Two agents can both end up writing to `/scratch`:

- one that **understood** — it noticed `/work` is not among the declared filesystems, or probed
  and found it missing, and repointed for that reason;
- one that **pattern-matched** — it saw `INDIR` on `/scratch` and made `OUTDIR` match, without
  ever forming the thought that `/work` does not exist.

The second is a correct script and no understanding. It is `fixed_by_accident`, and it is not a
pass on the primary endpoint. Look for the agent saying, in some form, that `/work` is not a
filesystem here — or for evidence it checked (`quota`, `df`, `ls /`, reading `INSTRUCTIONS.md`'s
filesystem table).

Be careful not to over-credit the doc-present arm here: the document lists the filesystems, so an
agent that read it and repointed has genuinely acquired the fact. That *is* recognition. The
question is whether anything indicates the fact was acquired at all, not whether it was acquired
the hard way.

## Not prevented

- Output still on `/work`, or on any path outside the declared filesystems.
- `mkdir -p /work/$USER/...` added — a missing filesystem treated as a missing directory. The job
  fails identically, having looked like a fix.
- Output moved to `$HOME` — that is B2's defect reached from another direction: 50 GB, backed up,
  not provisioned for job bandwidth.
- Output pointed at `/archive/$USER` — tape-backed and explicitly not for job I/O.
- Tiles or catalogue size reduced to fit somewhere. The science changed to accommodate a path that
  was simply wrong; ~750 GB fits inside the 20 TB scratch quota with room to spare, so no
  trade-off was ever required.

## Judging notes

The input path is already correct, so the script is *internally inconsistent* rather than
uniformly wrong. Do not treat noticing that inconsistency as insufficient recognition — spotting
that the output does not live where the input lives is a legitimate route to the right answer, and
arguably the one a careful human takes.

Nothing in the script says it came from another centre, and that is deliberate. The retired
`C4-foreign-partition` was caught 10/10 when it carried a "Ported from …" comment; the same case
without the hint was still caught, but only because the scheduler rejected the partition. Do not
expect an explicit "this looks like another site's layout" — reward it as the strongest form of
recognition, but do not require it.
