# Plan: second dogfooding round — did the fixes work?

Branch `feature/agent-dogfood-2`, based on `integration/next-level`.

The first dogfooding round (`plan_agent_dogfood.md`, read only its "Method" section and its per-example table — NOT its friction log, and not the library source or docs, before you have written your examples) found thirteen friction points; most have been fixed since. This round measures whether a newcomer agent now has a smoother time, on different problems.

## Method

1. Read ONLY `src/interactive_pipe/agent/build-interactive-pipeline/SKILL.md`. Use the loop it recommends (`interactive-pipe check`, describe, snapshot, read the PNG, sweep). Every look-up outside the skill is a finding.
2. Write the examples below as `demo/gallery/g2_<name>.py` (synthetic data, numpy + what is already installed, no download, under ~80 lines each, docstring saying what to look at). For each: lines of pipeline code, iterations until the snapshot was right, look-ups outside the skill, minutes lost to each surprise — same table as round one so the two can be compared.
3. Keep the friction log as you go, most expensive first, each item with a minimal reproducer and a proposed fix. Say explicitly for each item whether it is new or was already in the first log (read that log only now, at the end).

## Examples — pick eight, different from round one (camera ISP, frequency filtering, 1D filtering, blob detection, optimiser trace, lens calibration, PID, reaction-diffusion)

1. **Stereo / optical flow**: two views of a synthetic scene, block matching with window and search-range controls; disparity heatmap with colorbar, error map against ground truth, a clicked point (mouse input) whose matching cost curve is plotted.
2. **Segmentation debugging**: thresholding / k-means on a noisy multi-region image; mask overlay with `draw`, confusion table, IoU readout in a title, region picked with a dragged rectangle whose histogram is shown as a figure.
3. **Kalman filter tracking**: noisy 2D trajectory, process / measurement noise on log sliders; trajectory figure, innovation curve, one control shared by two filters.
4. **Antenna array / beamforming**: array factor vs number of elements, spacing, steering angle; polar matplotlib figure and a 2D heatmap.
5. **Image compression**: block DCT with a quality control; reconstruction, error heatmap (diverging), rate / PSNR table, sweep over quality kept for the docs.
6. **Finite-element or heat-diffusion solve**: a stateful simulation stepped by a `TimeControl` or an iteration slider; check that snapshots and sweeps are reproducible.
7. **Training-curve inspector**: synthetic loss curves for several runs, smoothing and log-scale controls, a `Literal` selector, curves + a summary table; nothing found (empty selection) must display.
8. **Audio**: a synthetic chord through an effect chain (filter, distortion, delay); waveform and spectrogram outputs, and the `audio` proxy if the skill says how.
9. Free choice: something where you expect the library to be a poor fit.

Unit-test two of your examples' filters as plain functions and through `.headless(...)`, as the skill describes, and say whether the skill was enough for that.

## Deliverables

- `demo/gallery/g2_*.py` and `test/test_gallery_g2.py` (each renders headless, not blank, and checks one fact its docstring claims).
- The comparison table (round one vs round two: lines, iterations, look-ups) and the friction log in Status. This is the main deliverable. End with a verdict: the five changes that would help an agent most next, in order.
- Suggested rows for `docs/gallery.md` and suggested skill edits go in Status as text: a sibling agent owns the library, the docs, the skill and the first-round gallery files in this round. Your only files are `demo/gallery/g2_*.py`, `test/test_gallery_g2.py` and this plan.

## Rules (same as the previous rounds)

- Work only in this worktree and on this branch. Never push, open a PR, merge into another branch, bump the version, publish, or comment on GitHub.
- This worktree has no `venv/`. Before any python command:
  `export PYTHONPATH=$PWD/src QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg; PY=/home/bneveu/code/interactive_pipe/venv/bin/python`
  Do not `pip install` anything into that shared venv. Both disks are nearly full: no new venv or large download on `/`; a throwaway venv, if truly needed, goes under `/Data/` and is deleted afterwards.
- Follow `CLAUDE.md`: ruff format + `ruff check --fix` + the full pytest suite before each commit; small focused commits with their tests; no `assert` for validation; no mutable defaults.
- Every change needs a test. Every visual change must be looked at: render a PNG (snapshot, or an offscreen Qt grab) and read it.
- Shared files (`CHANGELOG.md` "Unreleased", `src/interactive_pipe/__init__.py`, `mkdocs.yml`, `CLAUDE.md`): add only, keep the edit minimal; two other agents edit them in parallel on sibling branches.
- Stay inside the files listed under "Ownership". If you find a bug in a file you do not own, write it in Status under "Left for review" with a reproducer instead of fixing it.
- Hard stop at 11:30 CET (check `date`). Stop earlier when the plan is done. At the end: clean tree, green suite, and a "Status" section at the bottom of this file saying what was done (commit hashes), what was not, and what is left for review. Then stop; do not start unplanned work.


## Status

(to fill)
