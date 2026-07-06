# Inline Parameter Syntax (Alternative Style)

> **Note**: This is the most concise syntax for quick prototyping, but can be harder to maintain in production code. For production use, consider the [decorator parameter syntax](#decorator-parameter-syntax-production-recommended) instead.

## What is the Inline Parameter Syntax?

The inline parameter syntax is a very concise way of defining interactive parameters directly in the function signature:

```python
from interactive_pipe import interactive

@interactive()
def blend(img0, img1, blend_coeff=(0.5, [0., 1.])):
    '''Blends between two images'''
    return (1-blend_coeff)*img0 + blend_coeff*img1
```

In this approach:
- The decorator `@interactive()` has no parameters
- Control parameters are defined as tuples directly in the function signature
- The function receives the actual control values when called

## Trade-offs

This syntax is **ultra-concise** and great for quick prototypes, demos, and notebooks. However, it has some trade-offs for production code:

**Advantages:**
- ✅ **Most concise**: Everything in one place, minimal boilerplate
- ✅ **Quick to write**: Perfect for rapid prototyping and interactive demos
- ✅ **Self-contained**: Parameter specs right where you see the function

**Production considerations:**
- ⚠️ **Mixing concerns**: Function signature combines runtime defaults with GUI specifications
- ⚠️ **Type hints**: Defining parameters as tuples conflicts with proper type hints
- ⚠️ **Reusability**: Less clear which parameters are for interactivity vs core functionality
- ⚠️ **Maintenance**: Parameter specifications are less explicit in larger codebases

## Decorator Parameter Syntax (Production Recommended)

Use the **decorator parameter syntax** instead:

```python
from interactive_pipe import interactive

@interactive(blend_coeff=(0.5, [0., 1.]))
def blend(img0, img1, blend_coeff=0.5):
    '''Blends between two images'''
    return (1-blend_coeff)*img0 + blend_coeff*img1
```

### Benefits for Production Code:

1. **Separation of concerns**: GUI configuration is in the decorator, function logic is clean
2. **Better readability**: Clear distinction between interactive parameters (in decorator) and regular parameters
3. **Type hints friendly**: Function signature can have proper type hints
4. **Reusability**: The underlying function remains usable without the interactive wrapper
5. **Maintainability**: Easier to understand and modify in larger codebases

## Using Control Objects

For more control over widget behavior, use `Control` objects:

```python
from interactive_pipe import interactive, Control

@interactive(
    blend_coeff=Control(0.5, [0., 1.], name="blend coefficient")
)
def blend(img0, img1, blend_coeff=0.5):
    '''Blends between two images'''
    return (1-blend_coeff)*img0 + blend_coeff*img1
```

The tuple syntax `(default, [min, max], name)` is a convenient shorthand for `Control(default, [min, max], name=name)`.

## Choosing the Right Syntax

**Use inline syntax when:**
- Quick prototyping or demos
- Working in notebooks
- Code is short and self-contained
- Speed of writing is most important

**Use decorator syntax when:**
- Building production code
- Working in larger codebases
- Type hints are important
- Code maintainability is a priority

## Migration Guide

To migrate from inline syntax to decorator syntax:

### Before (Inline Style):

```python
@interactive()
def exposure(img, coeff=(1., [0.5, 2.], "exposure"), bias=(0., [-0.2, 0.2])):
    return img*coeff + bias

@interactive()
def black_and_white(img, bnw=(True, "black and white")):
    return np.repeat(np.expand_dims(np.average(img, axis=-1), -1), img.shape[-1], axis=-1) if bnw else img
```

### After (Decorator Style):

```python
@interactive(
    coeff=(1., [0.5, 2.], "exposure"),
    bias=(0., [-0.2, 0.2])
)
def exposure(img, coeff=1., bias=0.):
    return img*coeff + bias

@interactive(bnw=(True, "black and white"))
def black_and_white(img, bnw=True):
    return np.repeat(np.expand_dims(np.average(img, axis=-1), -1), img.shape[-1], axis=-1) if bnw else img
```

### Steps:

1. Move parameter specifications from function signature to decorator
2. Replace tuple defaults in function signature with simple default values
3. Ensure default values in function signature match the first element of the tuple

## Examples

For reference examples of the inline syntax, see:
- [samples/decorated_pipeline_abbreviated.py](/samples/decorated_pipeline_abbreviated.py)

For decorator syntax examples, see:
- [samples/decorated_pipeline.py](/samples/decorated_pipeline.py) - Using Control objects
- [readme.md](/readme.md) - Quick start examples with tuple syntax
- [samples/readme.md](/samples/readme.md) - Tutorial examples

## Full Support

Both syntaxes are fully supported and will continue to work. Choose the one that best fits your use case:
- **Inline syntax**: Maximum conciseness for prototypes and demos
- **Decorator syntax**: Better maintainability for production code

There's no rush to migrate existing code - both styles are equally valid from a functionality perspective. The choice depends on your specific needs and context.
