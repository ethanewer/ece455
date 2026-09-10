---
name: external-review
description: "Run an external review or audit over changes via the cursor-agent CLI. Three separate reviews: software-quality (Cursor bugbot, run before committing), scientific-correctness (physical model accuracy, realistic noise parameters, scoring math), and a deep auto-research audit of the whole pipeline. Pick the review that matches your change; run them as separate invocations. The reviewer returns text only and never edits files."
---

# External review (cursor-agent via CLI)

Runs an external reviewer over changes or over the whole pipeline, using
Cursor's `cursor-agent` CLI in print mode. Findings only; the reviewer never
edits project files.

## Pick a review

| What you are changing | Review to run |
|---|---|
| Code, netlists, or docs; about to commit | 1. software quality (bugbot) |
| A physical model, physical constants, noise parameters, scoring or estimator math, or docs that make physics claims | 2. scientific correctness |
| Both of the above in one diff | 1 and 2, as separate invocations |
| A large pipeline change, before starting an optimizer on the score, or periodically as a checkpoint | 3. deep auto-research audit |

Never fold two review types into one prompt; a physics finding can hide
behind a code finding and vice versa. When in doubt run the scientific
review too: a scoring bug that makes a result 1000x wrong is worse than a
code bug, and it is invisible to bugbot.

## Invoke

`cursor-agent` is on PATH at `~/.local/bin/cursor-agent`. Use the full path
if PATH misses it. Always run with the repo root as workspace:

```bash
cursor-agent -p -f --trust --workspace /Users/ethanewer/ece455 "<prompt>"
```

- `-p` print mode: non-interactive, the reviewer's reply goes to stdout. That
  reply is the report. Use the text default (`--output-format text`).
- `-f` pre-approves shell/git calls; drop it to prompt per call.
- `--trust` skips the workspace prompt.
- `--workspace` is the git root `/Users/ethanewer/ece455`. The active project
  `proton-magnetometer-autoresearch` and the project goals in
  `week2/report.md` are both inside it, so one workspace covers review and
  its reference context.
- Add `--model <model>` to pick a reviewer model (optional).

A review often runs minutes. If the session has the `monitor` skill or a
background watcher tool, run the invocation under it and keep working; do not
poll. Otherwise block in bash with a generous timeout.

## Review 1: software quality (bugbot)

Cursor's bugbot review subagent over the diff. Run before committing:

```bash
cursor-agent -p -f --trust --workspace /Users/ethanewer/ece455 \
  "Use the review-bugbot skill. Launch one bugbot subagent (run_in_background=false).
   Full Repository Path: /Users/ethanewer/ece455
   Diff: uncommitted changes
   The subagent computes the diff itself — do not precompute it. Report findings as a Severity | file:line | Finding table, sorted by severity (high first). Do not fix anything."
```

- `Diff: uncommitted changes` reviews only dirty working-tree edits; use
  `branch changes` for committed+staged+unstaged vs the base branch.
- Expected results: empty diff means "nothing to review"; no issues means one
  line such as "Bugbot found no bugs"; otherwise a
  `Severity | file:line | Finding` table, high first.

## Review 2: scientific correctness

A plain cursor-agent review (not bugbot). Run whenever the diff touches the
physics or the score. Full prompt:

```bash
cursor-agent -p -f --trust --workspace /Users/ethanewer/ece455 \
  "Read-only external review of the uncommitted changes under proton-magnetometer-autoresearch. If the tree is clean, review the most recent commit instead and say which you did.
   You are checking scientific correctness, not style.
   1. State the physical model each change encodes: units, constants, assumptions.
   2. Check every physical constant against CODATA/literature values, including bare vs shielded proton gyromagnetic ratio, and check unit conversions end to end (T/uT/nT, Hz per nT, noise-band Hz). A wrong comment next to a right constant is still a finding.
   3. Check noise parameters for realism: source impedance, amplifier e_n/i_n against datasheets, band limits, sample rate, aliasing, noise bandwidth. Flag any noise or signal parameter that is an injection rather than derived from the given hardware (e.g. assumed FID amplitude or T2*).
   4. Check estimator and statistics claims: re-derive or sanity-check CRBs against closed forms (Rife-Boorstyn), verify Monte-Carlo RMS sits at or above a valid bound within its CI, and confirm SNR definitions are named and consistent across tables.
   5. Check docs vs code: every formula, constant, and table in docs must match the code that produces the headline numbers. Flag anything an optimizer would exploit because the score ignores it.
   6. Run code where cheap (Monte-Carlo, SPICE parse, unit checks). Use /tmp for scratch. Never edit project files. Do not write anything into docs/ or docs/audit-feedback; that directory holds example output from other reviews, not yours.
   Return your report as text in your reply only: a one-paragraph verdict; a Severity | file:line | Finding table (high first); a list of the checks you ran with numeric results. Do not fix anything."
```

## Review 3: deep auto-research audit

Whole-pipeline audit in the style of the reports under
`proton-magnetometer-autoresearch/docs/audit-feedback` (those files are
example output from other review runs; your audit returns text, it does not
create files there). Full prompt:

```bash
cursor-agent -p -f --trust --workspace /Users/ethanewer/ece455 \
  "Full read-only audit of the autoresearch pipeline in proton-magnetometer-autoresearch. No project files change as part of this audit.
   1. Read docs/architecture.md, docs/research/*, all of poc/, and week2/report.md.
   2. Independently verify: re-execute every headline number in the README and architecture tables (CRBs, estimator RMS, SPICE noise) on this machine; re-derive the analytic bounds the code claims to implement; hand-check constants and unit paths (gyromagnetic conversion in Hz/nT, noise integrals, band consistency between the analytic and SPICE layers).
   3. Scientific accuracy: is the score a faithful model of the hardware it claims to score? What does the score ignore that the research docs say dominates real error (systematics, tuned topology, blanking recovery, gain topology)? What would an optimizer grind because nothing punishes it?
   4. Alignment: map each week-2 priority to what the pipeline actually scores; flag over-claims.
   5. Completeness: name any decision-relevant result that is not re-runnable from the tree (references to /tmp, estimators present in docs but absent from poc/).
   Return your report as text in your reply only: verdict paragraph; a table of independently verified checks with results; numbered scientific-accuracy issues; numbered alignment gaps; a priority-ordered fix list. Do not create or edit any files, including under docs/audit-feedback. Do not fix anything."
```

## Treating results

Advisory, not truth. Verify each finding before acting: agree with evidence
or refute it. A finding you cannot confirm is not a fix. The reviewer does
not auto-fix, and neither should you forward its findings into edits without
confirming them yourself.
