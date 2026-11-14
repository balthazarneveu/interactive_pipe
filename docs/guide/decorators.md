# Decorators

The two entry points of the library: `@interactive` declares the controls on a filter, `@interactive_pipeline` turns the function chaining the filters into a GUI application. `block` and `pipeline` are top-level aliases of `interactive` and `interactive_pipeline` respectively, so you can write `@ip.block(...)` / `@ip.pipeline(...)` after `import interactive_pipe as ip`.

There is also a one-shot `@interact` decorator for quickly opening a GUI on a single function — see [Tips & tricks](tips.md#one-shot-gui-with-interact).

## What a pipeline body may contain

The pipeline function is never executed: its body is parsed to build the execution graph. Each top-level statement must be one of:

| Statement | Example |
|---|---|
| Docstring, `pass`, `...` | `"""Denoise then sharpen."""` |
| Filter call, assigned or not | `out = blur(img)`, `a, b = split(img)`, `log_stats(img)`, `noise = generator()` |
| Nested call | `out = sharpen(blur(img))` — the inner output is named `blur(img)` (shown as its title) |
| Literal keyword argument | `out = blur(img, radius=3)` — sets this instance's value; when `radius` has a control it becomes that widget's default (must be within its range) |
| Dotted call | `out = np.abs(img)`, `out = lib.blur(img)` |
| One final `return` | `return out`, `return a, b`, `return [[a, b], [c, None]]`, `return blur(img)` |

Names are looked up where the function is defined (its closure, then its module), so a pipeline and its filters can live inside `main()` or a test function.

Anything else raises `PipelineSyntaxError` (a `ValueError`) when the pipeline is built, naming the file, the line and how to fix it:

```text
PipelineSyntaxError: pipeline 'my_pipe', /path/app.py, line 24: `if` statements are not supported in a pipeline function
    if flag:
Hint: move the condition inside a filter: give the filter a control (e.g. `@interactive(enabled=(True,))`) and branch in the filter body
```

Rejected constructs include `if` / `for` / `while` / `with` / `try`, arithmetic and any other expression that is not a call (`b = a * 2`, `img[0]`), `+=`, comprehensions, lambdas, a statement after `return`, `*args` / `**kwargs`, positional literals (`blur(img, 3)` — write `blur(img, radius=3)`), variables as keyword values (the body is not executed), builtins such as `print`, and unknown names (with a "did you mean" suggestion).

## What a filter returns, what a call returns

- A filter returning a tuple gives one value per name its pipeline line
  assigns: `a, b = split(img)`. A mismatch (`a = split(img)` with
  `return x, y`) raises `FilterError` naming the line.
- A list is one value: `detections = detect(img)` receives the list whatever
  its length (empty included). Return a tuple to unpack.
- Calling a `gui=None` pipeline, or `my_pipeline.headless(img, gain=2.0)` for
  any `gui=`, returns a tuple of the outputs in `return` order (a list of rows
  when the function returns a 2D list), whatever `layout.grid` displays.
  Keyword arguments set parameters like a slider move (kept for the next
  calls); an unknown name raises `TypeError`.
- `snapshot` / `sweep` start each picture from a fresh `context` (`runs=N` to
  warm up a stateful pipeline), see [Snapshots](snapshots.md).

::: interactive_pipe.interactive

::: interactive_pipe.interactive_pipeline
