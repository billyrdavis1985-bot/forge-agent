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

The engineering is built around one discipline: **make it harder for the instrument to mislead the researcher, while making
failures observable, traceable, and auditable.**

- **Two enforcement layers, sandboxed by default.** A software permission guard
  (removes shell access, path-jails all writes) *and* an OS-level bubblewrap
  sandbox (`sandbox.sh`, kernel-enforced), both verified by live probe. All
  execution paths — manual (`run.sh`), the systemd service, and the queue drain
  — converge through `flock -> bubblewrap -> orchestrator`, so the agent is
  jailed by default, not only when the sandbox launcher is invoked directly.
- **Evidence chain.** Every critic response is captured below the agent, hashed
  at the source, and pinned to the exact model digest and code/data git SHAs.
  Any run is independently verifiable; accidental corruption and naive tampering
  are detectable. (Provenance records live in the agent's writable domain, so a
  coordinated in-boundary rewrite is not yet defended against — see docs.)
- **Reproducibility, verified.** The instrument was found *non*-reproducible
  under naive settings — verdicts flipped across identical runs. Diagnosed
  (Ollama determinism needs pinned `num_ctx` + greedy decoding) and fixed; repeated runs were byte-reproducible under the tested
  model/Ollama/runtime configuration. Caught before any finding was trusted.
- **Control-plane boundary.** Untrusted critic output cannot reach the agent's
  decision context as prose — only parsed tokens cross. The tool-return channel
  is closed and tested. (The agent retains read access to staged files, so the
  full information-flow channel is not yet closed — see docs.)
- **Governance spine.** The agent stages judgments for human review; it never
  scores or decides whether a diagnosis is genuine.

 ## Quickstart

Requires Linux or WSL2, Python 3.10+, [bubblewrap](https://github.com/containers/bubblewrap),
and [Ollama](https://ollama.com) with your critic models pulled.

```bash
# 1. Install and test — no API key or SDK needed for the test suite
python3 -m venv .venv
.venv/bin/pip install pytest pytest-asyncio PyYAML
.venv/bin/python -m pytest tests/ -q          # 51 tests, all offline

# 2. Bootstrap the agent's memory from templates
cp memory/CLAUDE.md.example        memory/CLAUDE.md
cp memory/open_questions.md.example memory/open_questions.md
cp config/agent.yaml.example        config/agent.yaml
cp .env.example .env                           # then add your ANTHROPIC_API_KEY

# 3. Prove the sandbox holds — before trusting it
./sandbox_probe.sh                             # watch the kernel refuse out-of-bounds writes

# 4. Run one bounded, sandboxed session
.venv/bin/pip install -r requirements.txt      # the Claude Agent SDK
./run.sh "your task"                           # routes through flock -> bwrap -> orchestrator
```

The agent's `memory/` is a separate private git repo; only the machinery is
published here, so you supply your own mission and tasks via the templates above. 

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

## Verify the claims yourself

This project's ethos is *don't trust, verify* — so every safety claim above is a
runnable demonstration, not an assertion:

```bash
./sandbox_probe.sh                 # kernel refuses writes outside the sandbox
.venv/bin/python -m pytest tests/  # 51 tests: guard policy, evidence chain,
                                   #   control-plane boundary, budget ceiling,
                                   #   queue, tool containment, adjudication
.venv/bin/python -m src.verify memory   # re-hash every critic response; a run
                                   #   is VERIFIED only if the evidence chain holds
```

The guard tests include the exact escape that once succeeded against an earlier
version (a write reaching the real repo), now blocked and regression-tested.

## Requirements

Linux (or WSL2). Python 3.10+, bubblewrap, Ollama, and the Claude Agent SDK. The
agent's memory is a separate private git repo; only the machinery is published.

## Known limitations

Claims here are scoped to what the code proves. Deferred hardening, tracked
honestly rather than overstated:

- **Evidence custody.** Provenance records live in the agent's writable domain,
  so hashing detects accidental corruption and naive tampering — not a
  coordinated in-boundary rewrite. A custodian outside the agent's write
  authority is future work.
- **Information-flow channel.** The tool-return channel that could carry critic
  prose into the agent is closed and tested; the agent still retains read access
  to staged files, so the full channel is not yet sealed.
- **Scale.** Findings are from a small grid (two critics). The methodology is the
  contribution; the numbers are illustrative, not a general benchmark.

## Status

A working, tested instrument. Not affiliated with or endorsed by any model
vendor. Research code.
