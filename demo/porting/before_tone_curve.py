"""Fit a camera tone curve (gamma + offset) to noisy measurements and apply it to an image."""

import matplotlib.pyplot as plt
import numpy as np

TRUE_GAMMA = 2.2
NOISE = 0.02
DEGREES = [1, 3, 5]

rng = np.random.default_rng(3)
exposure = np.linspace(0.01, 1, 40)
measured = exposure ** (1 / TRUE_GAMMA) + rng.normal(0, NOISE, exposure.shape)

results = {}
for degree in DEGREES:
    coefs = np.polyfit(exposure, measured, degree)
    fitted = np.polyval(coefs, exposure)
    results[degree] = {"coefs": coefs, "fitted": fitted, "rmse": np.sqrt(np.mean((fitted - measured) ** 2))}

x = np.linspace(0, 1, 256)
ramp = np.tile(x, (64, 1))

plt.figure(figsize=(10, 4))
plt.subplot(1, 2, 1)
plt.plot(exposure, measured, "k.", label="measured")
for degree, res in results.items():
    plt.plot(exposure, res["fitted"], label=f"deg {degree} rmse={res['rmse']:.3f}")
plt.legend()
plt.xlabel("exposure")
plt.subplot(1, 2, 2)
best = min(results, key=lambda d: results[d]["rmse"])
plt.imshow(np.clip(np.polyval(results[best]["coefs"], ramp), 0, 1), cmap="gray")
plt.title(f"ramp through deg {best}")
plt.show()
