from interactive_pipe.data_objects.curves import Curve
import numpy as np

# from interactive_pipe import interact


# Note:
# --------------------------------------------------------------------------
# You can also use the disable flag and leave the decorator code uncommented...
# @interact(frequency=(3., [0, 10.], "freq[Hz]"), phase=(90.,[-180, 180], "phase °"), disable=True)
# Or you can decorate it afterwards, like in the main
# interact(frequency=(3., [0, 10.], "freq[Hz]"), phase=(90.,[-180, 180], "phase °"), disable=True)(generate_sine_wave)


# !! Uncomment to get a graphical interface test... !!
# @interact(frequency=(3., [0, 10.], "freq[Hz]"), phase=(90.,[-180, 180], "phase °"))
def generate_sine_wave(
    frequency=1,
    phase=0.0,
) -> Curve:
    x = np.linspace(0.0, 1.0, 100)
    crv = Curve(
        [
            [
                x,
                np.cos(2.0 * np.pi * frequency * x + np.deg2rad(phase)),
                "k-",
                f"sinewave {frequency:.1f}Hz\nphase={int(phase):d}°",
            ],
            [
                x,
                np.cos(2.0 * np.pi * frequency * x),
                "g--",
                f"sinewave {frequency:.1f}Hz",
            ],
        ],
        xlabel="time [s]",
        ylabel="value",
        ylim=[-1.0, 1.0],
        grid=True,
        title="Oscillator",
    )
    return crv


def switcher(
    img1: np.ndarray,
    img2: np.ndarray,
    img3: np.ndarray,
    img4: np.ndarray,
    choice: int = 0,
    amplify: float = 1.0,
) -> np.ndarray:
    return amplify * [img1, img2, img3, img4][choice], img4


# here's another nice little "main" you can leave
# to visually check that your filter works correctly.

# if __name__ == '__main__':
#     from interactive_pipe import interact
#     interact(gui="qt", frequency=[0, 10.], phase=[-180, 180])(generate_sine_wave)
