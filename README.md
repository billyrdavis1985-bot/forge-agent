# Forge Agent

[![CI](https://github.com/billyrdavis1985-bot/forge-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/billyrdavis1985-bot/forge-agent/actions/workflows/ci.yml)

An autonomous research agent for evaluating fine-tuned reasoning critics — built
as a hardened, reproducible instrument, and a deliberately small precursor to a
larger autonomous-research system.

Forge runs locally-hosted critic models against batches of deliberately-corrupted
reasoning samples, stages each verdict against ground truth, and characterizes
each critic's failure profile — unattended, sandboxed, and without the agent
itself ever judging whether a verdict is genuinely correct.

## What makes it notable

The engineering is built around one discipline: **make it impossible for the
instrument to fool the researcher.**

- **Two independent enforcement layers.** A software permission guard (removes
  shell access, path-jails all writes) *and* an OS-level bubblewrap sandbox
  (kernel refuses out-of-bounds writes even if the guard fails). Both verified
  by live probe.
- **Evidence chain.** Every critic response is captured below the agent, hashed
  at the source, and pinned to the exact model digest and code/data git SHAs.
  Any run is independently verifiable; tampering is detectable.
- **Reproducibility, verified.** The instrument was found *non*-reproducible
  under naive settings — verdicts flipped across identical runs. Diagnosed
  (Ollama determinism needs pinned `num_ctx` + greedy decoding) and fixed;
  runs are now byte-reproducible. Caught before any finding was trusted.
- **Control-plane boundary.** Untrusted critic output cannot reach the agent's
  decision context as prose — only parsed tokens cross. Prompt-injection across
  the model boundary is closed and tested.
- **Governance spine.** The agent stages judgments for human review; it never
  scores or decides whether a diagnosis is genuine.

## A finding it produced

Under byte-reproducible decoding, paired perturbation analysis of two fine-tuned
critics showed **disjoint blind spots** (each misses corrupted items the other
catches) and that one critic **over-flags on a majority of pairable problems** —
it cannot distinguish a sound proof from its corrupted twin. Two problems defeat
both critics identically (a shared, architecture-independent failure). All
classifications are verdict-level and reproducible; whether they reflect genuine
reasoning is left to human reading.

## Architecture

| Component | Role |
|---|---|
| `src/orchestrator.py` | Preflight, budget gate, sandboxed agent loop, ledger, health |
| `src/guards.py` | Software enforcement: write containment, tool gating |
| `src/agent_tools.py` | Bounded tools: `run_critic`, `run_critic_batch`, `append_log` |
| `src/provenance.py` | Evidence chain: immutable records, hashing, verification |
| `src/verify.py` | Independent run verifier |
| `src/ledger.py` | SQLite operations record + daily budget ceiling |
| `src/queue.py` | Task queue for unattended drains |
| `sandbox.sh` / `sandbox_probe.sh` | OS-level bwrap jail + its probe |
| `drain.sh` | Unattended queue drain (resumes after sleep) |
| `build_dashboard.py` | Audit surface: failure-shape analysis, no scoring |
| `perturbation.py` | Paired clean-vs-corrupted discrimination analysis |
| `adjudicate.py` | Blinded human-adjudication protocol |
| `docs/feedback-loop-principle.md` | Guardrail for any future training loop |

## Requirements

Linux (or WSL2). Python 3.10+, bubblewrap, Ollama, and the Claude Agent SDK. The
agent's memory is a separate private git repo; only the machinery is published.

## Status

A working, tested instrument. Not affiliated with or endorsed by any model
vendor. Research code.
