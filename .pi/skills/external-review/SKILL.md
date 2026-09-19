---
name: external-review
description: "Run read-only software, scientific, and design-consistency reviews with Cursor CLI for this single-design proton magnetometer repository."
---

# External review with Cursor CLI

Use this skill to obtain an independent review of the active proton magnetometer design and its verification code. This repository develops one design. Reviewers must not propose search loops, candidate ranking, mutation systems, or unattended research workflows.

The reviewer reports findings only. It must not edit files, create reports in the repository, commit changes, or alter generated design artifacts.

## Repository scope

Review the current directories according to their roles:

| Path | Role |
|---|---|
| `receiver_design/` | Active ngspice model, generated analysis reports, KiCad connectivity, and EDA verification scripts |
| `verification_modeling/` | Python physics, noise, CRB, coil, circuit-format, and ngspice code |
| `frequency_estimator_firmware/` | Portable C estimator, host binding, mirror implementation, and golden vectors |
| `tests/` | Python regression tests |
| `docs/coil-design.md` | Current coil assumptions and provenance |
| `docs/verification-plan.md` | Bench and acceptance plan |
| `docs/reference/` | Background reports, not active specifications |
| `.github/workflows/ci.yml` | Automated software, firmware, and ngspice checks |

Treat `docs/current_work/`, `docs/past_work/`, `docs/resources/`, and `docs/week_2/` as source or historical material. Do not treat historical values as active requirements unless an active document or implementation cites them.

## Choose a review

| Change | Review |
|---|---|
| Python or C implementation, tests, parsers, process execution, Makefile, or CI | Software quality |
| Physics, constants, units, noise, CRBs, signal generation, coil values, or acceptance limits | Scientific correctness |
| ngspice, KiCad, or component-value changes | Design consistency, plus scientific correctness if claims or models changed |
| A change spanning several rows | Run each applicable review separately |
| Explicit repository-wide audit | Full design-verification audit |
| Prose-only or image-only change with no technical claim | No external review by default |

Do not combine software and scientific reviews into one prompt. Separate reports make each finding easier to verify.

## Invocation

The executable is normally `~/.local/bin/cursor-agent`. Run it from the repository workspace:

```bash
~/.local/bin/cursor-agent -p -f --trust \
  --workspace /Users/ethanewer/ece455 "<prompt>"
```

- `-p` prints the response without starting an interactive session.
- `-f` pre-approves shell and Git calls. Remove it when per-command approval is required.
- `--trust` skips the workspace confirmation.
- `--workspace` must remain `/Users/ethanewer/ece455`.
- `--model <model>` selects a reviewer model when requested.

Reviews may take several minutes. Run them with the process monitor when available, and do not poll them. Run review types one at a time. Concurrent Cursor review sessions have stalled without producing reports. Redirect each report to a file under `/tmp`, then read it after the process exits.

By default, review uncommitted changes. If the working tree is clean, review the latest commit and state that choice. Use a comparison against `main` only when the user requests a branch-wide review.

## Software-quality review

Use this for changes to `verification_modeling/`, `frequency_estimator_firmware/`, receiver Python scripts, `tests/`, the Makefile, or CI.

```bash
~/.local/bin/cursor-agent -p -f --trust \
  --workspace /Users/ethanewer/ece455 \
  "Use the review-bugbot skill. Launch one bugbot subagent with run_in_background=false.
   Repository: /Users/ethanewer/ece455
   Scope: uncommitted changes. If there are none, review the latest commit and say so.
   This is a single-design proton magnetometer repository. Do not recommend automated search or research-loop infrastructure.
   Review correctness, error handling, determinism, subprocess safety, numerical edge cases, portability, stale paths, and missing regression tests.
   Check interfaces among verification_modeling, frequency_estimator_firmware, receiver_design Python scripts, tests, Makefile, and CI.
   Run cheap tests when useful. Use /tmp for scratch files.
   Do not edit or create repository files.
   Return either 'No findings' or a Severity | file:line | Finding table sorted by severity, followed by commands run."
```

## Scientific-correctness review

Use this when a change affects physical models, constants, units, signal generation, noise, estimator statistics, coil parameters, or acceptance criteria.

```bash
~/.local/bin/cursor-agent -p -f --trust \
  --workspace /Users/ethanewer/ece455 \
  "Perform a read-only scientific review of the uncommitted changes in /Users/ethanewer/ece455. If there are none, review the latest commit and say so.
   This repository verifies one proton magnetometer design. Do not evaluate or propose design-search infrastructure.
   1. State each affected physical model, its units, constants, and assumptions.
   2. Check constants against primary references. Distinguish bare and water-shielded proton gyromagnetic ratios. Trace T, uT, nT, Hz, and Hz/nT conversions end to end.
   3. Check coil source impedance, Johnson noise, amplifier voltage and current noise, bandwidth, sample rate, aliasing, quantization, clipping, and noise integration.
   4. Identify nominal or injected values that still require measurement, including FID amplitude, T2 star, mutual inductance, polarizer field, ring-down, PSRR, and recovery.
   5. Re-derive CRBs or compare them with a valid closed form. Confirm simulation or Monte Carlo results do not beat a valid bound beyond numerical and confidence-interval tolerance. Check that SNR definitions are explicit and consistent.
   6. Compare verification_modeling, receiver_design, frequency_estimator_firmware, docs/coil-design.md, and docs/verification-plan.md. Flag conflicting formulas, constants, component values, and claims.
   7. Run cheap calculations and tests without modifying the repository. Use /tmp for scratch files.
   Do not edit or create repository files.
   Return a verdict, a Severity | file:line | Finding table sorted by severity, and checks run with numeric results."
```

## Design-consistency review

Use this after ngspice, KiCad, or component-value changes.

```bash
~/.local/bin/cursor-agent -p -f --trust \
  --workspace /Users/ethanewer/ece455 \
  "Perform a read-only consistency review of the active design under receiver_design.
   Review the uncommitted changes. If there are none, review the latest commit and say so.
   1. Compare component values, net names, signal stages, assumptions, and interfaces across receiver_design/spice/receiver.cir, generated analysis reports, KiCad files, verification_modeling/coil.py, and active documentation.
   2. Run python3 receiver_design/verify.py when ngspice or KiCad is installed. Report skipped tools rather than claiming a pass.
   3. Treat DRC as a connectivity and geometry check only. Identify missing active devices, protection, switching, ADC, clock, power, connectors, footprints, and layout review where applicable.
   4. Separate simulated behavior, DRC results, nominal assumptions, and measured evidence.
   5. Check that committed reports correspond to the exact committed source artifact and are not stale.
   Do not edit or create repository files.
   Return a verdict, a Severity | file:line | Finding table sorted by severity, and commands run."
```

## Full design-verification audit

Use only for an explicit repository-wide audit or a change spanning modeling, design, firmware, and acceptance criteria.

```bash
~/.local/bin/cursor-agent -p -f --trust \
  --workspace /Users/ethanewer/ece455 \
  "Perform a full read-only verification audit of /Users/ethanewer/ece455.
   This repository develops one proton magnetometer design. Do not propose automated search, candidate ranking, mutation, or unattended research workflows.
   1. Read README.md, docs/README.md, docs/coil-design.md, docs/verification-plan.md, verification_modeling, frequency_estimator_firmware, receiver_design, tests, Makefile, and CI.
   2. Run make test and make firmware. Run python3 receiver_design/verify.py --require-tools only when both external tools are installed; otherwise run it without --require-tools and report skips.
   3. Independently check key constants, units, coil calculations, noise calculations, resonance, ring-down, ADC behavior, estimator bounds, and golden-vector provenance.
   4. Trace active values across documentation, Python models, ngspice, generated reports, KiCad, firmware, and tests. Identify stale or conflicting copies.
   5. Separate verified software behavior, simulated behavior, nominal hardware assumptions, and measured hardware evidence.
   6. Identify missing tests, weak failure checks, incomplete hardware, stale reports, and claims unsupported by measurement.
   Do not edit, create, or commit repository files. Use /tmp for scratch files.
   Return a verdict, a table of checks with numeric results, findings sorted by severity, and a priority-ordered fix list."
```

## Handle findings

Treat every report as advisory. Confirm each finding using code, active documentation, a derivation, or a reproducible command before changing the repository. Record why a finding is valid or invalid. Do not apply a proposed fix without confirming the underlying issue.
