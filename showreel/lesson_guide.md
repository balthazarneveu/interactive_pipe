# Lesson guide: from a demo that runs to a demo that teaches

What the show reel rounds taught, beyond the API covered by the agent skill
(`interactive-pipe skill`). Read it together with `house_rules.md` when writing
a teaching demo.

## Caching: never hand-roll it

`@interactive_pipeline(cache="graph")` recomputes a filter only when its own
controls, its inputs or a `context` key it reads changed. Split the graph so
that this does the work: `dataset -> train -> render` means a display checkbox
on `render` does not retrain and a training slider does not rebuild the
dataset. Do not write module-level dict caches. `pipeline.last_run_report`
(`.timings`, `.cached`, `.total`) tells what ran and how long it took: check it
instead of assuming (call a pipeline without inputs twice, then read
`.cached`).

A refresh should stay well under a second; with Qt, `threaded=True` keeps
widgets live during slower runs. Small PyTorch models and small linear solves
are often several times slower with the default thread pools: call
`torch.set_num_threads(1)` at the top of a PyTorch demo, and keep numpy solves
to a few hundred unknowns. With a cache, filter outputs are copied: return
numpy arrays or detached tensors, never tensors still attached to an autograd
graph, so do the forward and backward passes inside one filter.

## Animation

```python
@interactive(time=TimeControl(update_interval_ms=40))
def clock(time=0.0):
    return int(time * FPS) % N_FRAMES  # the frame index flows to the filters that draw
```

Simulate once in an upstream filter; only the drawing filters depend on the
frame. Map time to a frame with fixed constants (`FPS`, `DURATION`), not with a
slider value, and loop with a modulo.

`export_animation(headless_pipeline, "out.gif", duration=5.0, fps=10.0, output=(row, col))`
renders a GIF without a window. It records one output, which must be an image
(not a `Curve`). In the GUI, `v` exports the first image. When a GIF is asked
for, offer a command-line path:

```python
GIF = next((arg for arg in sys.argv[1:] if arg.endswith(".gif")), None)  # python demo.py out.gif


@interactive_pipeline(gui=None if GIF else "auto", cache="graph")
def demo(): ...


if __name__ == "__main__":
    demo()  # opens the window, or runs once headless when a GIF path is given
    if GIF:
        export_animation(demo, GIF, duration=DURATION, fps=FPS, output=(0, 0))
```

## Pictures that read well

- Drawing on an image without `interactive_pipe.draw`: build shapes as masks on
  a coordinate grid, `mask = np.hypot(X - x0, Y - y0) < radius`, rather than
  indexing at computed coordinates, where a negative index silently wraps to
  the other side.
- Render maps, scatters and drawings at 300 to 400 px (compute coarse and
  upsample with `np.kron` when needed).
- Fix `vmin` / `vmax` and `xlim` / `ylim` when the picture should not rescale
  while a slider moves; leave headroom in `ylim` for the legend.
- Per-sample bars on a `Curve` are stems drawn as one polyline broken by NaNs:
  `x = np.stack([t, t, t * np.nan], 1).ravel()`,
  `y = np.stack([0 * w, w, w * np.nan], 1).ravel()`.

## Quality bar for a demo

A demo that runs is not yet a lesson. Before declaring it done, go through this
list with rendered pictures (`snapshot`, `sweep`) and printed numbers, not from
memory of the code.

**The lesson**
- Open the file with a 3 to 6 line docstring: the idea, the equations that
  matter, what to look at. Explain magic constants in a comment. Every claim in
  the docstring and the titles must hold at the slider ends: check it.
- Each thing the request says students should see must show at the defaults or
  one slider move away. Render each one separately and print the number that
  proves it. If the numbers contradict the story, the model is wrong (a missing
  bias term, too few features, a blend that never reaches its target), not the
  lesson: fix the model.
- **When the request says *why* something matters, or names a trade-off or a
  "too low / too high" regime, showing the correct result is not enough.** Give
  a way to do it wrong (a dropdown applying a stage in the wrong order, a toggle
  removing the fix) and a number or plot exposing the consequence. Sweep the
  parameter in its own filter, fed only by what the sweep depends on so the
  cache keeps it when other sliders move, and plot it as a `Curve` with the
  current setting as a red dot; for under-fit / over-fit the held-out metric
  must peak strictly inside the slider range.
- A control that is the remedy (pre-filter, regularization, stabilization)
  applies it fully at its default, and its other end shows the failure plainly:
  the picture must change, not only a number in a title. When the request says
  "from none to fully X", the end really reaches X, not the end of a blend
  towards something intermediate.
- Choose content the effect can bite on and whose correct look is known: smooth
  areas, sharp edges and fine texture together; grey patches for anything about
  colour; a reference drawn in (a limit circle, the exact orbit, the ideal
  curve, the true centres).

**The picture**
- Every returned output has a title. Titles carry the numbers that matter
  (PSNR, loss, zoom needed); axes have labels; discrete items (tokens, classes,
  methods) are named, not numbered.
- Keep `Curve` titles under about 45 characters. Choose `ylim` so the default
  regime is fully visible; clip values into it only for truly divergent
  settings, so a curve rides the edge instead of leaving the plot. Draw the
  reference line last so it stays visible.
- Show the current selection (keyboard-stepped item, current time, current
  setting) in every view that displays it: a frame drawn into the heatmap, a
  vertical line or a dot on the curve.
- In an animation, keep the end result visible in a static panel or in a title,
  so a slider's effect shows without waiting for the loop.

**The code**
- Write the pipeline so it reads as the story: one filter per concept, named
  after it.
- A value computed upstream flows downstream as an extra output
  (`decoded, rate = encode(coefficients)`); never recompute a step inside a
  later filter to recover one of its results.
- Sweep each slider to both ends and the middle, and look: the interesting
  regime should cover most of the range, not a sliver of it. Narrow the range
  otherwise.
- Measure the refresh (`last_run_report.total`) at the defaults and at the
  heaviest slider settings; shrink ranges or sizes until it stays under a
  second.
- Verify the maths numerically (identity at zero, known limits, a
  finite-difference check of a closed form).
