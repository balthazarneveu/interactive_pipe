import logging
from urllib.request import urlretrieve
from pathlib import Path
import tempfile
from typing import Union
from interactive_pipe.data_objects.parameters import Parameters
from interactive_pipe.data_objects.image import Image
import os
OPENAI_SUPPORT = True
try:
    import openai
except ImportError:
    OPENAI_SUPPORT = False
    logging.warning("openai not installed, please install it with pip install openai")


class ImageFromPrompt(Image):
    """A useful class to generate an image from a prompt using openai image API

    Warning:
    - The open AI service costs a few cents per request.
    - You need to know what you're doing here, refer to https://platform.openai.com/
    to get an account and check billing options.
    - For obvious reasons: Internet access is mandatory for obvious reasons

    An API token is required or to be provided directly when calling the class.
    To be more convenient, user can set OPENAI_API_KEY in their os environment variables
    - such as ~/zsh.rc under linux
    - in the global environment variables under windows

    Here's an example on how to use this class.
    ```python
    img = ImageFromPrompt(
        "a smiling elephant in a modern kid book drawing style on a white background",
        path="images/elephant_openai.png"
    )
    img.show()
    ```
    Some more info https://github.com/balthazarneveu/interactive_pipe/issues/27
    """
    SUFFIX = ".png"

    @staticmethod
    def check_file_existence(pth: Union[str, Path]) -> Union[bool, Path]:
        if pth is None:
            return False
        if isinstance(pth, str):
            pth = Path(pth)
        return pth.exists()

    @staticmethod
    def download_file(image_url, output=None, suffix: str = SUFFIX) -> Path:
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
        assert OPENAI_SUPPORT, "openai not installed"
        if api_key is not None:
            openai.api_key = api_key
            openai.organization = organization
            assert ImageFromPrompt.__check_login(), "cannot log in"
            return
        if openai.api_key is not None:
            # SKIPPING!
            logging.info("Already logged in to openai")
            # ImageFromPrompt.__check_login()
            return
        if api_key is None:
            api_key = os.getenv("OPENAI_API_KEY")
            openai.api_key = api_key
            openai.organization = organization
            ImageFromPrompt.__check_login(), "cannot log in"

    @staticmethod
    def __check_login():
        assert OPENAI_SUPPORT, "openai not installed"
        assert openai.api_key is not None
        try:
            response = openai.Model.list()
            logging.debug(
                f"available api models: {','.join([item['id'] for item in response['data']])}")
            return True
        except openai.error.OpenAIError as e:
            logging.error(e.http_status)
            logging.error(e.error)
            return False

    @staticmethod
    def __generate_image_to_disk(prompt, path=None, size=(256, 256), api_key=None, silent=False) -> Path:
        assert isinstance(prompt, str), f"{prompt}"
        if ImageFromPrompt.check_file_existence(path):
            logging.info(f"Already cached image {path}")
            if not isinstance(path, Path):
                path = Path(path)
                path = path.with_suffix(ImageFromPrompt.SUFFIX)
            return path
        assert OPENAI_SUPPORT, "openai not installed"
        try:
            # You need the API key at this moment
            ImageFromPrompt.login(api_key=api_key)
            if not silent:
                logging.warning(
                    f"Requesting the open AI API with prompt : {prompt} & {size}\nThis will cost you a few cents")
            response = openai.Image.create(
                prompt=prompt,
                n=1,
                size=f"{size[0]}x{size[1]}"
            )
            image_url = response['data'][0]['url']
            if not silent:
                print(f"Download image URL {image_url}")
            out_file = ImageFromPrompt.download_file(image_url, output=path)
            params = Parameters({"prompt": prompt, "url": image_url, "path": str(
                out_file), "response": response})
            params.save(out_file.with_suffix(".yaml"))
            return out_file
        except openai.error.OpenAIError as e:
            logging.error(e.http_status)
            logging.error(e.error)
            return None

    @staticmethod
    def generate_image(prompt, path: Union[str, Path], size=(256, 256), api_key=None):
        assert path is not None, "To avoid not knowing where you generated your images , providing a path is mandatory"
        path = ImageFromPrompt.__generate_image_to_disk(prompt, path=path, api_key=api_key, size=size)
        print(f"Image generated at {path}")
        return path

    def __init__(self, prompt, path: Union[str, Path], size=(256, 256), api_key=None) -> None:
        file_path = ImageFromPrompt.generate_image(
            prompt, path=path, api_key=api_key, size=size)
        super().__init__(None, title=prompt)
        self.path = file_path
        self.data = self._load(file_path)
