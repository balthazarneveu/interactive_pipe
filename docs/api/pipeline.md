# Pipelines

The decorators that build a pipeline, the pipeline object they return, and the
errors raised while building or running it. See the [Decorators](../guide/decorators.md)
and [Snapshots & sweeps](../guide/snapshots.md) guides for usage.

## Decorators

::: interactive_pipe.interactive

::: interactive_pipe.interactive_pipeline

::: interactive_pipe.interact

## Pipeline object

`@interactive_pipeline(gui=None)` returns a `HeadlessPipeline`;
`HeadlessPipeline.from_function(fn)` builds one without the decorator. GUI
pipelines expose `snapshot`, `sweep`, `describe` and `summary` too, and every
`@interactive` filter has `.snapshot()`, `.sweep()`, `.describe()`,
`.summary()` and `.interact(img)` running it alone.

::: interactive_pipe.HeadlessPipeline
    options:
      members:
        - from_function
        - __call__
        - run
        - snapshot
        - sweep
        - describe
        - summary
        - save
        - export_tuning
        - load_tuning
        - graph_representation

## Static types

What the decorators return, for annotations and type checkers (mypy,
pyright). `@interactive` keeps the filter's signature and return type
(`amplify(img, gain=2.0)` is checked against `amplify`'s own parameters);
`@interactive_pipeline(gui=None)` is typed as a `HeadlessPipeline`, any other
`gui` as a `GuiPipelineApp`. See [Type checking](../guide/type-checking.md).

::: interactive_pipe.InteractiveFilter

::: interactive_pipe.PipelineApp

::: interactive_pipe.GuiPipelineApp

::: interactive_pipe.PipelineDecorator

::: interactive_pipe.export_animation

## Errors

::: interactive_pipe.PipelineSyntaxError

::: interactive_pipe.FilterError
    options:
      members: false

::: interactive_pipe.graphical.display.DisplayError
