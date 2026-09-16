# Cursor optimization-agent iteration

Use this workflow only when the user requests a Cursor agent as the candidate proposer.

## Setup

- Expect `cursor-agent` at `~/.local/bin/cursor-agent` or on `PATH`.
- Use `/Users/ethanewer/ece455` as the trusted workspace so the agent can read the project and its design references.
- Confirm the requested model identifier is supported before a long run.

## Bounded invocation

Run one iteration with an explicit proposal-only prompt:

```bash
~/.local/bin/cursor-agent -p -f --trust \
  --workspace /Users/ethanewer/ece455 \
  --model grok-4.6 \
  "Work in proton-magnetometer-autoresearch. Propose and evaluate one candidate iteration. Read README.md, docs/architecture.md, docs/runbook.md, and docs/coil-design-week3.md first. You may change candidate parameters or proposal artifacts. Do not edit pipeline/evaluate.py, verifier gates, physical constants, test thresholds, or validation fixtures. Preserve hardware_characterized=False in production data. Return the exact candidate, commands run, score, every gate, and remaining qualification limits."
```

Treat the model's output as a proposal. Inspect the diff and reproduce its score locally before accepting it.

## Stopping conditions

Stop after the requested iteration count. Stop early if the proposal attempts to change the verifier, suppress a failed gate, mark hardware as characterized, or reports a score that cannot be reproduced.

If the accepted proposal changes verifier code, run the applicable external reviews. Candidate-only, documentation, screenshot, and PCB-export work does not require those reviews.
