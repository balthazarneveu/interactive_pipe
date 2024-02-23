from interactive_pipe import interact
from filters_library import generate_sine_wave

if __name__ == '__main__':
    # here's another nice little main you can leave
    # to visually check that your filter works correctly.
    interact(frequency=[0, 10.], phase=[-180, 180])(generate_sine_wave)
