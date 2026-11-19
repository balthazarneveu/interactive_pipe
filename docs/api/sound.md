# Audio helpers

`from interactive_pipe import sound` — pure numpy functions to load, analyse
and transform 1D audio signals inside filters; play the result with the
[`audio` proxy](context.md). See [Audio](../guide/audio.md#audio-helpers-interactive_pipesound)
for an example and `demo/audio_processing_demo.py` for a complete app.

::: interactive_pipe.sound
    options:
      show_root_heading: false
      members:
        - load
        - to_mono
        - normalize
        - resample
        - stft
        - istft
        - spectrogram
        - spectrogram_style
        - add_noise
        - snr_db
        - denoise
        - time_stretch
        - pitch_shift
