# Decorators

The two entry points of the library: `@interactive` declares the controls on a filter, `@interactive_pipeline` turns the function chaining the filters into a GUI application. `block` and `pipeline` are top-level aliases of `interactive` and `interactive_pipeline` respectively, so you can write `@ip.block(...)` / `@ip.pipeline(...)` after `import interactive_pipe as ip`.

There is also a one-shot `@interact` decorator for quickly opening a GUI on a single function — see [Tips & tricks](tips.md#one-shot-gui-with-interact).

::: interactive_pipe.interactive

::: interactive_pipe.interactive_pipeline
