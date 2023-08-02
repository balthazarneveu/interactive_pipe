import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent/"src"/"interactive_pipe"))
import logging
logging.warning("using local version without pip installer")