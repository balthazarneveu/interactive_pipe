import logging
from urllib.request import urlretrieve
from pathlib import Path
import tempfile 
from typing import Union
from interactive_pipe.data_objects.parameters import Parameters
from interactive_pipe.data_objects.image import Image
import os
import openai

class ImageFromPrompt(Image):
    SUFFIX = ".png"
    @staticmethod
    def check_file_existence(pth: Union[str, Path]) -> Union[bool, Path]:
        if pth is None:
            return False
        if isinstance(pth, str):
            pth = Path(pth)
        return pth.exists()
    @staticmethod
    def download_file(image_url, output=None, suffix: str=SUFFIX) -> Path:
        if output is None:
            output = tempfile.mktemp(suffix=suffix)
        if not isinstance(output, Path):
            output = Path(output)
        if not output.parent.exists():
            output.parent.mkdir(exist_ok=True, parents=True)
        urlretrieve(image_url, output)
        assert output.exists()
        return output
    
    @staticmethod
    def login(api_key=None, organization=None):
        if openai.api_key is not None:
            logging.debug("Already logged in to openai")
            return
        if api_key is None:
            api_key = os.getenv("OPENAI_API_KEY")
        assert api_key is not None
        openai.organization = organization
        openai.api_key = api_key
        openai.Model.list()

    @staticmethod
    def generate_image(prompt, output=None, size=(256, 256), debug=True) -> Path:
        assert openai.api_key is not None
        assert isinstance(prompt, str), f"{prompt}"
        if ImageFromPrompt.check_file_existence(output):
            logging.warning(f"Already cached image {output}")
            if not isinstance(output, Path):
                output = Path(output)
                output = output.with_suffix(ImageFromPrompt.SUFFIX)
            return output
        try:
            response = openai.Image.create(
                prompt=prompt,
                n=1,
                size=f"{size[0]}x{size[1]}"
            )
            image_url = response['data'][0]['url']
            if debug:
                print(image_url)
            out_file = ImageFromPrompt.download_file(image_url, output=output)
            params = Parameters({"prompt": prompt, "url": image_url, "path": str(out_file), "response": response})
            params.save(out_file.with_suffix(".yaml"))
            return out_file
        except openai.error.OpenAIError as e:
            logging.error(e.http_status)
            logging.error(e.error)
            return None
    
    @staticmethod
    def generate_image_to_disk(prompt, path=None, api_key=None):
        ImageFromPrompt.login(api_key=api_key)
        path = ImageFromPrompt.generate_image(prompt, output=path)
        return path
    
    def __init__(self, prompt, path=None, api_key=None) -> None:
        file_path = ImageFromPrompt.generate_image_to_disk(prompt, path=path, api_key=api_key)
        super().__init__(None, title=prompt)
        self.path = file_path
        self.data = self._load(file_path)
    
