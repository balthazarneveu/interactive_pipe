# Contributing to interactive_pipe

Contributions are welcome! Open a [GitHub issue](https://github.com/balthazarneveu/interactive_pipe/issues) to report a bug or discuss a feature before starting a large change.

## Development setup

```bash
git clone git@github.com:balthazarneveu/interactive_pipe.git
cd interactive_pipe
python -m venv venv
./venv/bin/pip install -e ".[dev,pytest,full]"
```

## Quality gates

Run all of these before committing — the CI runs the same checks:

```bash
./venv/bin/python -m ruff format .          # format
./venv/bin/python -m ruff check --fix .     # lint (auto-fix)
./venv/bin/python -m pyright                # type check (informational, non-blocking)
./venv/bin/python -m pytest test/ -v --tb=short
```

## Conventions

- **Small, focused commits**: one logical change per commit; bundle test changes with the source changes they cover.
- **PRs target `master`**.
- **Docstrings**: Google style (`Args:` / `Returns:` / `Example:` sections) — they feed the generated API reference.
- **Exceptions over asserts**: raise `TypeError` / `ValueError` / `RuntimeError` for runtime validation.
- **Pipeline functions contain only function calls**: the AST parser builds the execution graph from the pipeline function body, so no if/else/for/while or arithmetic there — put logic inside filters.

## Documentation

The docs site is built with MkDocs Material:

```bash
./venv/bin/pip install -e ".[docs]"
./venv/bin/python -m mkdocs serve
```

Architecture notes for anyone digging into the core live in [code_architecture.md](https://github.com/balthazarneveu/interactive_pipe/blob/master/code_architecture.md).
