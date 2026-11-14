# Broken pipelines

Each script has one realistic bug whose symptom is visual or silent. The
docstring states the symptom only, as a user would report it. They are not
collected by pytest (no `test_` prefix). They are a corpus for checking the
debugging tools by hand (`interactive-pipe check`, `snapshot`, `sweep`, the
skill): no test asserts yet that each tool points at the cause.
