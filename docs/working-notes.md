# HPC skills project — working notes

Participants: Corentin, Kangning, Alex, Louis-Felix, Debbie

## Rationale

**What**: a shared skill set teaching an agent to operate a cluster: module system, job
submission, job control and monitoring (`squeue`, poll/tail policy, job-state
determination, reporting), resource estimation from the scripts, submit-vs-run-inline
classification, and a "don't do this" list (starting with filesystem abuse).

**Why**: today `lc run` fails on module load and needs an interactive job for
everything. This is the cheapest large win available.

**Who / help needed**: Debbie volunteered to write the GitHub issue and to own the
don't-do-this half; Kangning and Steffen both have working skills to contribute.

**Effort**: 1–2 hours. Blocker addressed: agents are incompetent cluster citizens.

## Existing skills to build upon

- <https://github.com/nipreps/skills-comm/blob/main/plugins/job-monitor/SKILL.md>
- <https://github.com/LightconeResearch/agent-skills/tree/feat/async-job-skills/skills/estimate>
- <https://github.com/LightconeResearch/agent-skills/tree/feat/async-job-skills/skills/classify-run>
- <https://github.com/HolobiomicsLab/hpc-session>
- <https://github.com/argonne-lcf/alcf-agent-skillset>

## The flow of running a job

- **Discover the platform** → HPC intro skills at a fixed certain location?
- **Preparing the environment**
  - Load modules: need to know available modules
  - Specific user instructions, e.g. load a specific conda?
- **Estimate the cost**
  - Knowing the hardware → reference from HPC platform
  - Identify the limiting factor, e.g. CPU or GPU or mem, etc. → estimation skill
  - Running small jobs to extrapolate the cost → estimation skill
- **Submit and monitoring the job**
  - Submit to the right queue → reference from HPC platform, classification skill?
  - Monitoring the job → reference from HPC platform

## On HPC side

A read-only document on a standardized path to provide agents (and humans) with useful
information to put in context before running jobs on the platform.

The markdown file should be short, concise, yet state what are the main computing
resources available and state clearly the boundaries for agents. Links to extended
documentation can be provided in the form of other markdown files in an extra folder or
documentation websites.

### Location

- `/agents/INSTRUCTIONS.md` ← read-only
- `/agents/extra/failure_modes.md`
- `/agents/extra/feedback_template.md`

### Template

```markdown
# Instructions for <center name>

## About us

### Nodes

Login Nodes
CPU Nodes
    CPU AMD xxxx
    Mem xxGB

GPU Nodes
XXX Nodes

See [link to the doc] for more information

### File systems

Home: what to use it for, default allocation, how to request more
Tape archive: what to use it for, default allocation, how to request more
Scratch: what to use it for, default allocation, how to request more
XXX

### Environments

.bashrc (or equivalent) defaults
Module commands
Virtual environments
Package managers (conda/uv/pixi)

### Containers

Docker / podman / apptainer / singularity

### Other Software

See [link to the doc] for more information

## Running Jobs

### Scheduler

Slurm (with some notes on cluster-specific commands if needed)

### Queues

| Queue   | Max node | Max time | QOS factor |
|---------|----------|----------|------------|
| Regular | 2        | 24 h     | 1          |

### Charges

Most Users have a fixed budget of allocations, see [link to the doc] for how the
allocations are charged.

### Required user-specific information

Account, queue, resources, ...

## Documentation

Link to the living documentation (website)

## Guardrails

Whatever you do, make sure you
- never send more than 1 request every 1 minute to the Slurm controller, otherwise it
  will be overwhelmed.
- never read or write thousands of small (<1MB) files on any file system, otherwise you
  will see degraded performance.
- never use the login nodes for compute jobs or to store data.

## Best Practices for more efficient use of the HPC center

How to configure your compute job to get through the queue faster
How to install your code in the right place for best performance
Where to place your data for best performance
How to place your processes in a multi-node job for best performance

## Feedback

Tell here whether the platform accepts feedback from the agent on the jobs that ran on
the platform (e.g. after analysis of the traces) and if so where to put that information
and in which form (template `/agents/extra/feedback_template.md`)
```

## Project outputs

- Webapp artefact producing and/or validating a template `INSTRUCTIONS.md` file for HPC
  centers to implement
- Skill for agents to interact with these HPC centers through these instructions

## Possible extension

- RAG-bot hosted on the computing center and available both for agents or users to
  answer questions about usage stored in the `INSTRUCTIONS.md`
- Bot hosted on the computing center with knowledge from the current status/usage of the
  nodes
