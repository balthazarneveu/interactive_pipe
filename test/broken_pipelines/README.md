# Broken pipelines

Each script has one realistic bug whose symptom is visual or silent. The
docstring states the symptom only, as a user would report it. They are not
collected by pytest (no `test_` prefix); `test/test_broken_pipelines.py` runs
the debugging tools on them and asserts each tool points at the cause.
