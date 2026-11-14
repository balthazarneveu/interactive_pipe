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
- `tools/grade.py`: runs a demo headless, sweeps every control, dumps the default outputs.

## Skill-improvement loop

The prompts double as an evaluation set for `.claude/skills/build-interactive-pipeline`.

1. A Sonnet agent receives `prompt.md` + `house_rules.md`, with the skill as its only documentation, and writes `demo.py`.
2. `tools/grade.py` checks the result: pipeline body made of calls only, no removed API, runs headless, every control changes an output, no NaN, refresh time, line budget.
3. The outputs and the agent's friction log are reviewed. What the agent had to guess or look up is fixed in the skill, never in the prompt.
4. The attempt is compared with the reference in `demos/`, which was written with full access to the library source and held to the same grader.

`11_attention` and `03_jpeg` are held out: they are only run once the skill has been tuned on the others, to check that the skill generalizes.

## Running

```bash
python showreel/demos/camera_rotation.py              # opens the GUI
python showreel/tools/grade.py showreel/demos/camera_rotation.py --out /tmp/grade_camera_rotation
```

Demos 09 and 10 need PyTorch (CPU is enough).
