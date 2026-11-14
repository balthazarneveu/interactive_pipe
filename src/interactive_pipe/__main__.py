"""``python -m interactive_pipe``: same as the ``interactive-pipe`` command."""

import sys

from interactive_pipe.agent.command_line import main

if __name__ == "__main__":
    sys.exit(main())
