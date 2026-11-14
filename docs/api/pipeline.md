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

::: interactive_pipe.headless.pipeline.HeadlessPipeline
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

::: interactive_pipe.export_animation

## Errors

::: interactive_pipe.PipelineSyntaxError

::: interactive_pipe.FilterError
    options:
      members: false

::: interactive_pipe.graphical.display.DisplayError
