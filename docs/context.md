# Agentic AI for Science: Summit Notes Synthesis

> Source: [Google Doc](https://docs.google.com/document/d/1SploxMDsDmMhnSHTgV4EDkfdrZLSLTFVCERvyJUHxSc/edit)

## Core Vision & Goals

The summit aims to create a **roadmap for widespread adoption of agentic AI in scientific
research**. Key themes include trust, verification, provenance, research infrastructure,
agent architecture, and domain science applications.

## Major Project Initiatives

### 1. HPC Skills for Agents

**Goal**: Enable agents to operate computing clusters competently by teaching them module
systems, job submission, monitoring, and resource estimation.

**Current gap**: Agents cannot load modules and require interactive jobs for all tasks.

**Deliverables**:
- Shared skill set covering Slurm job control, resource estimation, and "don't do this"
  guardrails
- Effort: 1-2 hours
- Addresses: "Agents are incompetent cluster citizens"

### 2. Research Infrastructure & Compute Access

**Key challenges identified**:
- Compute resources lack discoverability across facilities
- Agents need location-agnostic execution without account management overhead
- Cross-facility, account-less access remains policy-intensive

**Proposed solutions**:
- Markdown-based resource descriptions (not APIs) per HPC center
- Bounded containerized environments for long-running autonomous tasks
- Unified interface standards via "American Science Cloud"

### 3. Trust, Verification & Provenance

**Critical gaps**:
- Current systems produce fast analyses but lack clear verification pathways
- Need to capture decisions, failed attempts, and reasoning traces
- "Nanopublications" concept: break articles into smaller, referenceable, updatable
  pieces linked as computational graphs

**Requirements**:
- Separate scientific provenance (what built on what) from accountability (human
  responsibility)
- Automated verification agents that re-check results against new data
- Credit/attribution tracking for human and AI contributions

### 4. Agent Architecture & Scientist Interfaces

**Core principle**: "The scientific question stays the North Star. Agents are
instruments inside science, not the point of it."

**Key tensions**:
- Tool vs. collaborator framing debate
- Need to preserve human understanding and joy in research, not automate friction away
- Exposed reasoning traces essential; vendors hiding them problematic

**Design priorities**:
- Natural-language interfaces with predictable, characterized error behavior
- Mentor-style scaffolding (not just answer-dispensing)
- Composable, protocol-based layers (MCP, ACP) over vendor lock-in

### 5. Domain Science Applications

**Adoption barriers**:
- Limited concrete examples from domain scientists using agents
- Observability challenge: understanding agent assumptions, decisions, failures
- Verification burden: analyzing outputs requires substantial expert time

**Proposed solution**: Personalized, shareable research notebooks transforming agent
histories into digestible formats highlighting assumptions and review needs.

## Key Technical Standards & Patterns

### Markdown-Based HPC Instructions Template

Centers should publish `/agents/INSTRUCTIONS.md` containing:
- Node types, filesystems, queues, resource charges
- Guardrails ("never send >1 Slurm request/minute")
- Best practices for efficient job placement and data handling
- Feedback mechanisms for agents

**Rationale**: Capable models rediscover correct approaches without over-specification;
human-editable; discoverable across harnesses.

### Nanopublications & ASTRA Spec

- Break scientific outputs into composable, referenceable pieces
- Link results as computational dependency graphs
- Enable continuous verification as new evidence arrives
- Support "living documents" that update post-publication

### Skill Benchmarking Needs

- Skills degrade with each model release (e.g., Opus 5 broke legacy skills)
- No shared general→specific skill hierarchy
- HPC-specific benchmarking currently missing

## Critical Unsolved Challenges

1. **Provenance at scale**: How to track decisions when one agent serves multiple
   humans; what happens when early decisions are revised?
2. **Knowledge loss prevention**: Pre-LLM knowledge stored only in model weights; how to
   surface origins when knowledge isn't publicly accessible?
3. **Sandbox design**: Current permission models force choice between unusable (prompt on
   every action) or completely open (dangerous defaults).
4. **Formal guardrails**: Need finite-state machine constraints on agent transitions
   without restricting legitimate capability.
5. **Account-less cross-facility access**: Policy and governance remain harder than
   technical implementation.

## Existing Resources to Build On

- **Academy** (Argonne): Agentic orchestration with provenance built-in
- **Open OnDemand, OpenCode, VS Code**: Interface layers with trace preservation
- **Slurm**: Existing permission/submission controls reusable for guardrails
- **American Science Cloud**: Cross-site benchmark infrastructure
- **Lightcone/lc run**: Async job monitoring and output tracking
- **Contributor Role Taxonomy (CRediT)**: Existing credit attribution framework

## Proposed Unconference Sessions

- Provenance for agentic science (accountability & credit)
- Managing long-running autonomous HPC tasks
- Open-source/open-weight models for science benchmarking
- AI as teaching agent (learning vs. answer-dispensing)
- Scientific workflow end-to-end mapping

## Failure Modes to Avoid

- Queue monopolization and allocation waste by agents
- Sandboxes so restrictive users disable them universally
- Loss of human accountability chains institutions require
- Maintenance-heavy tool surfaces obsoleted by model improvements
- Skill throwaway cycles at each model release
- Sensitive data leakage from TREs or air-gapped systems

---

**Overall Theme**: Moving from "can agents do science" to "how do we rebuild scientific
infrastructure (institutionally, technically, pedagogically) so agents enhance rather
than replace human understanding?"
