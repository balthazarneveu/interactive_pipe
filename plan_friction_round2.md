# Plan: fix what the second dogfooding round found

Branch `feature/friction-round2`, based on `integration/next-level`. Read the Status of `plan_agent_dogfood_2.md` in full first: its friction log (11 items, each with a reproducer), its verdict, its suggested skill edits and gallery rows are this plan. Also the "Left for review" of `plan_consolidate.md`. You own the whole repository in this round except `test/conftest.py` and anything about test isolation (a sibling agent is hunting a rare native crash there).

## Items, in the order of the log's verdict

1. **`layout.style` merges successive calls on one output within a run** (later call wins per key; an explicit `None` clears a key — decide and document). The "clipped to [0, 1]" warning must not suggest something already done. Test with the log's reproducer on snapshot, Qt offscreen, mpl.
2. **`audio.set(array, sample_rate)`** next to `audio.set(path)`: mono / stereo float or int16 arrays; the library writes the temporary WAV (cleaned up), wrong calls get a `TypeError` that shows both forms. Say in the docstring and the skill whether `play()` is needed and what happens when the signal changes. Headless and snapshot runs must not touch any audio device.
3. **`Curve` axes**: `xscale=` / `yscale=` (`"log"`, `"linear"`, maybe `"symlog"`) on `Curve`, working in snapshots and every backend that plots curves (Qt / DPG have their own curve widgets: check each). Then put the data-object keywords an agent had to guess in the skill (`Curve`, `SingleCurve`, `Table(precision=)`, `.columns` / `.values`, `draw.mask` alpha).
4. **Figures in sweeps**: with several outputs per sweep cell a figure's text shrinks to ~6 px, and a figure cell is drawn smaller and framed differently from the `Curve` next to it; long axes titles are clipped. Make figure cells and curve cells the same size and text size in snapshots *and* sweeps (render several layouts, read them). For a figure whose filter called `tight_layout()` at its own `figsize`: re-run the layout at cell size when the figure has no explicit layout engine (consolidation left this as a judgement call: do it unless it breaks a test, and say so). A sweep of N outputs per cell should lay the outputs out sensibly (e.g. four wide outputs as 2×2, not 4×1).
5. **Axes on heatmaps**: `layout.style(name, extent=(x0, x1, y0, y1), xlabel=, ylabel=)` drawn around the image the same way on every backend and in snapshots (same technique as the colorbar: drawn into the displayed image); the Qt pixel readout and `PointControl` values must still map to the right data pixel when margins are added (`display.heatmap_geometry`), and the readout should report extent coordinates when an extent is set.
6. **Readouts reachable in tests**: titles and styles set by filters during the last run available without a GUI — e.g. `pipe.styles` / `describe()["outputs"][i]["title"]` after a run, and on the object returned by `.headless`. Choose one small API, document it in the testing guide and skill.
7. Smaller items of the log: (6) the skill sentence on labels being names; (8) an unknown `on=` target in a `gui=None` pipeline: keep the build-time error for GUI pipelines but allow reuse of the filter in a small headless test pipeline (warning) — decide and justify; (9) styling an input: one sentence; (10) the context / re-run contract: verify with `cache=True` on, write the sentence, fix it if the contract does not hold; (11) snapshot caption names a shared control by its control name.
8. From consolidation's list: export `DisplayError` from `interactive_pipe` (it is raised to users); a bare `f(img)` line where `f` returns a value raises — it should just discard the value (the parser accepts unassigned calls); colorbar end label vs nearest tick nearly touching (`vmin=1.0`, max 4.2).
9. **Gallery**: add the eight `g2_*.py` examples to `docs/gallery.md`, `docs/guide/examples.md` and `scripts/make_gallery.py` (rows suggested in the log), remove the two `g2_*` filters the sibling added to the globs of `test/test_gallery.py` and `test/test_examples_page.py`, use the new features in the examples where they remove a workaround (heatmap axes instead of axes written in titles, `Curve(yscale="log")`, `audio.set(array, rate)`), regenerate the images and look at every one. Keep total size of `docs/images/gallery/` reasonable (report it).
10. Skill: apply the log's suggested edits that are still true after your fixes; keep within the line limit of `test/test_skill_code_blocks.py` by removing what both dogfooding rounds never needed; re-install the copy (`python -m interactive_pipe skill --install --project . --force`). Changelog: add to the existing themed sections (behaviour changes first, each with an upgrade-page link: `test/test_upgrade_page.py` enforces it).
11. `mkdocs build --strict` at the end (throwaway venv under `/Data/`, deleted after; skip if less than 2 GB would stay free).

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
