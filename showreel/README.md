# Show reel

Twelve short demos, one engineering lesson each. Every demo is a single file a student can read in five minutes, built from synthetic inputs.

| # | Demo | Lesson |
|---|---|---|
| 01 | `aliasing` | Low-pass before you decimate (Nyquist) |
| 02 | `camera_isp` | Stage order in a raw camera pipeline, linear vs gamma domain |
| 03 | `jpeg` | Rate/distortion, blocking artifacts |
| 04 | `integrator_stability` | Explicit Euler gains energy; symplectic and RK4 integrators |
| 05 | `camera_rotation` | A rotating pinhole camera warps the image by `K R K^-1` |
| 06 | `gyro_stabilization` | Stabilizing is counter-rotating; the zoom pays for the black borders |
| 07 | `volume_rendering` | Transmittance and weights along one ray (NeRF quadrature) |
| 08 | `fourier_features` | Spectral bias: why coordinate networks need positional encoding |
| 09 | `mlp_decision_boundary` | Capacity vs regularization (PyTorch) |
| 10 | `signal_propagation` | Vanishing/exploding signals, He/Xavier init, normalization (PyTorch) |
| 11 | `attention` | Softmax temperature, causal mask, position vs content |
| 12 | `diffusion` | Noise schedules and sampling steps, with an exact score |

## Layout

- `prompts/NN_name.md`: the request a user would type. It names the lesson, not the API.
- `demos/name.py`: the reference implementation, written independently of the evaluated attempts.
- `house_rules.md`: constraints shared by every prompt.
- `lesson_guide.md`: what the rounds taught about writing a demo that teaches (caching, animation, quality bar), kept out of the agent skill so that it stays short.
- `tools/grade.py`: runs a demo headless, sweeps every control, dumps the default outputs.

## Skill-improvement loop

The prompts double as an evaluation set for `.claude/skills/build-interactive-pipeline`.

1. A Sonnet agent receives the prompt and `house_rules.md`, with the skill as its only documentation (it may introspect the installed package, not read the repository), and writes `demo.py`. It ends with a friction log: what the skill did not say, said wrongly or left ambiguous.
2. `tools/grade.py` checks the result: pipeline body made of calls only, no removed API, runs headless, every control changes an output, no NaN, refresh time, line budget.
3. The outputs and the agent's friction log are reviewed. What the agent had to guess or look up is fixed in the skill, never in the prompt.
4. An Opus judge compares the attempt with the reference in `demos/` (written with full access to the library source and held to the same grader), looking at the rendered outputs. It scores lesson, completeness, idiom, readability and polish from 1 to 5, and says for each gap whether a sentence in the skill could have prevented it.

The grader only tells whether a demo works; after the first skill revision every attempt passed it. The judged comparison is what separates a working demo from a good lesson.

`11_attention` and `03_jpeg` were held out of the first two skill revisions and attempted for the first time in round 3; both passed the grader on the first try.

## Evaluation results (November 2026)

Sonnet, one attempt per prompt and per round, skill as only documentation. Judged scores are the sum of five 1-5 axes (lesson, completeness, idiom, readability, polish), so 25 is the maximum.

| Round | Skill | Passes the grader | Judged total (of 300) | Mean per axis |
|---|---|---|---|---|
| 1 (3 prompts) | 0.9.4 skill | 3 / 3, with a hardcoded backend, no cache and one hand-rolled cache | not judged | |
| 2-3 (12 prompts) | v2-v3: API facts | 12 / 12 | 205 | 3.4 |
| 4 | v4: lesson design rules | 12 / 12 | 224 | 3.7 |
| 5 | v6: more quality rules | 11 / 12 | 224 | 3.7 |

| Prompt | Rounds 2-3 | Round 4 | Round 5 |
|---|---|---|---|
| 01 aliasing | 20 | 22 | 21 |
| 02 camera_isp | 17 | 19 | 17 |
| 03 jpeg | 17 | 19 | 21 |
| 04 integrator_stability | 16 | 20 | 19 |
| 05 camera_rotation | 18 | 19 | 20 |
| 06 gyro_stabilization | 19 | 19 | 19 |
| 07 volume_rendering | 15 | 17 | 18 |
| 08 fourier_features | 14 | 15 | 14 |
| 09 mlp_decision_boundary | 17 | 17 | 18 |
| 10 signal_propagation | 17 | 19 | 18 |
| 11 attention | 17 | 20 | 20 |
| 12 diffusion | 18 | 18 | 19 |

What this says, with the caveat that each cell is a single run scored by a single judge, so a point or two is noise:

- **Stating API facts fixed correctness.** Before, agents hardcoded `gui="qt"`, did not know `cache=`, `Curve` or how to share a slider, and one wrote its own cache. Afterwards every attempt ran, used the cache and the default backend.
- **Lesson design rules gave the one measurable quality gain** (3.4 to 3.7): show how to do it wrong, sweep a trade-off into a curve with the current setting marked, pick content the effect can bite on.
- **More rules after that did not help** (round 5 equals round 4). What is left is specific to each subject (a missing bias term, a loss that mixes forward and backward effects, a title that does not match its frame) or is already in the skill and was not applied. The references score higher because their authors checked the maths and looked at the window, not because they knew more API.
- **The window has to be looked at.** Every reference passed the grader while its plots were 100 px high with their titles cut off in the Qt window. `tools/screenshot.py` exists for that reason.

## Running

```bash
python showreel/demos/jpeg.py                    # opens the GUI (best available backend)
python showreel/demos/jpeg.py -b mpl             # pick the backend: qt, dpg, mpl, gradio
python showreel/demos/jpeg.py -b headless        # run once without a window (smoke test)
python showreel/demos/gyro_stabilization.py out.gif   # animated demos export a GIF, no window
```

`gyro_stabilization`, `integrator_stability` and `diffusion` are animated: `p` pauses, `v` exports from the GUI. `mlp_decision_boundary` and `signal_propagation` need PyTorch (CPU is enough).

```bash
python showreel/tools/grade.py showreel/demos/jpeg.py --out /tmp/grade_jpeg --max-lines 70
python showreel/tools/scoreboard.py /path/to/runs    # one line per attempt of an evaluation folder
python -m pytest test/test_showreel.py               # every reference still passes its grader
```
