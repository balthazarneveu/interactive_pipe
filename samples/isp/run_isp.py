from pathlib import Path
from interactive_pipe import interactive_pipeline
from isp_filters import isp_pipeline, isp_monolithic_rawpipipeline
import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-b", "--backend", type=str, default="gradio", choices=["gradio", "qt", "mpl"])
    args = parser.parse_args()
    SAMPLE_PATH = Path(__file__).parent/'images'/'dji_mavic_3.dng'
    # SAMPLE_PATH = Path(__file__).parent/'images'/ 'canon_5d.CR2'
    # SAMPLE_PATH = Path(__file__).parent/'images'/'sony_rx100iv.ARW'
    isp_pipeline_gui = interactive_pipeline(gui=args.backend, cache=True)(isp_pipeline)
    # isp_pipeline_gui = interactive_pipeline(gui=args.backend, cache=True)(isp_monolithic_rawpipipeline)
    isp_pipeline_gui(SAMPLE_PATH)
