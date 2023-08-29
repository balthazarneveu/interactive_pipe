from interactive_pipe.headless.pipeline import HeadlessPipeline

class InteractivePipeGUI():
    def __init__(self, pipeline: HeadlessPipeline = None, controls=[], name="", custom_end=lambda :None, audio=False, **kwargs) -> None:
        self.pipeline = pipeline
        self.custom_end = custom_end
        self.audio = audio
        self.name = name
        if hasattr(pipeline, "controls"):
            controls += pipeline.controls
        self.controls = controls
        self.init_app(**kwargs)
        pipeline.global_params["__app"] = self
    
    def init_app(self):
        raise NotImplementedError
    
    def run(self):
        raise NotImplementedError