# 🛠️ API Reference - `jpipe_runner.framework`

This document provides an in‑depth reference of public classes, methods, decorators, and utilities exposed by the `jpipe_runner` framework. Contributors can use these details when extending functionality or debugging the pipeline.

## Class: `PipelineEngine` (in `jpipe_runner.framework.engine`)

**Module path:** `jpipe_runner.framework.engine`

**Description:**
Orchestrates loading, validating, and executing a justification pipeline. It builds a directed graph from a `.jd.json` file, validates dependencies, computes execution order, and invokes functions via a runtime.

### Constructor

```python
PipelineEngine(
    config_path: str,
    justification_path: str,
    mark_step: Callable[[Any, Any], None],
    mark_substep: Callable[[str, str, str], None],
    mark_node_as_graph: Callable[[str, str], None],
    variables: Optional[Iterable[Tuple[str, Any]]] = None
) -> None
```

| Parameter            | Type                                 | Description                                              |
|----------------------|--------------------------------------|----------------------------------------------------------|
| `config_path`        | `str`                                | Path to the YAML configuration file.                     |
| `justification_path` | `str`                                | Path to the justification `.jd.json` file.               |
| `mark_step`          | `Callable[[Any,Any],None]`           | Function to mark major steps in UI/visualizer.           |
| `mark_substep`       | `Callable[[str,str,str],None]`       | Function to mark substeps or status transitions.         |
| `mark_node_as_graph` | `Callable[[str,str],None]`           | Function to register a node as a sub-graph in UI.        |
| `variables`          | `Optional[Iterable[Tuple[str,Any]]]` | List of `(name, value)` overrides for context variables. |

**Behavior:**

1. Logs initialization and sets up `ctx._vars` with configuration and overrides.
2. Parses justification into a `networkx.DiGraph`, stored in `self.graph`.
3. Prepares `self.justification_name` and UI markers.

### Public Attributes

* `graph: nx.DiGraph` — Directed graph of workflow nodes and dependencies.
* `justification_name: str` — Human-readable name of the justification.

### Public Methods

#### `load_config(path: str, variables: Optional[Iterable[Tuple[str, Any]]] = None) -> None`

Loads a YAML configuration file into the global context and applies variable overrides.

* **Errors**: YAML parse errors are logged; do not raise exceptions here.

#### `parse_justification(path: str) -> nx.DiGraph`

Reads a justification JSON and builds a dependency graph.

* **Returns:** A `networkx.DiGraph` with nodes representing steps.

#### `get_producer_key(var: str) -> Optional[str]`

Determines which function produces a given variable.

* **Args:** `var` — Variable name to query.
* **Returns:** Function key string or `None` if not found.

#### `validate() -> bool`

Runs a suite of validators on the pipeline graph:

1. `MissingVariableValidator`
2. `SelfDependencyValidator`
3. `OrderValidator`
4. `ProducedButNotConsumedValidator`
5. `DuplicateProducerValidator`

* **Behavior:** Marks substeps in UI, aggregates errors and warnings.
* **Returns:** `True` if all checks pass; `False` otherwise.

#### `get_execution_order() -> List[str]`

Computes topological sort of `self.graph`.

* **Returns:** List of node IDs.
* **Errors:** If cycle detected, logs error and returns empty list.

#### `justify(runtime: PythonRuntime, dry_run: bool = False) -> Iterator[dict]`

Executes pipeline nodes in order:

1. Validates pipeline
2. Retrieves execution order
3. Processes each node via `_process_node`

* **Parameters:**

  * `runtime` — Instance to dynamically invoke functions.
  * `dry_run` — If `True`, skips actual function calls (marks PASS).

* **Yields:** Dictionaries with keys:

  * `name`, `label`, `var_type`, `status` (`PASS`, `FAIL`, `SKIP`), `exception`.

#### `export_to_format(status_dict: Dict[str,str], output_path: str, format: str) -> None`

Renders the pipeline graph to an image file (e.g., `png`, `svg`).

* **Args:**

  * `status_dict` — Mapping from node ID to status.
  * `output_path` — File path to save image.
  * `format` — One of supported Graphviz formats.

## Decorators (in `jpipe_runner.framework.decorators`)

### `@jpipe(consume: Optional[List[str]]=None, produce: Optional[List[str]]=None)`

Unified decorator to declare which variables a function **consumes** from, and **produces** to, the pipeline context.

```python
@jpipe(consume=["input_var"], produce=["output_var"])
def my_step(input_var: Any, produce: Callable[[str, Any], None]) -> bool:
    # function logic here
    produce("output_var", result_value)
    return True
```

| Parameter | Type        | Description                                           |
| --------- | ----------- | ----------------------------------------------------- |
| `consume` | `List[str]` | Variables to read from context before calling `func`. |
| `produce` | `List[str]` | Variables the function must set via `produce()` call. |

#### Wrapper Behavior

* **Registration**: At import time, registers declared `consume` and `produce` names with the global context.
* **Injection**: Before calling the original function, injects consumed values from `ctx` into `kwargs`.
* **Production**: Exposes a `produce(param, value)` callable in `kwargs`, allowing the function to set values.
* **Validation**: After execution, validates that all declared `produce` variables were set.

## Class: `ConsumedVariableChecker` (in `jpipe_runner.framework.decorators`)

Manages and validates variables declared under `consume`:

* **register\_variables()**: Marks variables in `ctx` as required.
* **inject\_arguments(kwargs) -> dict**: Inserts current values from `ctx` into function arguments.
* **\_get\_used\_variables() -> Set\[str]**: Parses the function source via AST to ensure declared variables are actually referenced.

Raises `ValueError` if a consumed variable is missing at runtime.

## Class `ProducedVariableChecker` (in `jpipe_runner.framework.decorators`)

Manages and validates variables declared under `produce`:

* **register\_variables()**: Declares output variables in `ctx`.
* **produce(param, value)**: Sets the variable in `ctx`; errors if undeclared.
* **validate\_produced()**: Ensures all declared variables were produced; logs errors otherwise.

Raises `RuntimeError` if undeclared or missing productions are detected.

## Exceptions

### `FunctionException` (in `jpipe_runner.exceptions`)

Raised when a decorated justification function returns an unexpected type or `False` indicating failure.

## RuntimeContext (in `jpipe_runner.framework.context`)

Manages all variable tracking for a pipeline run — including variables consumed, produced, skipped, and their contributions — on a per-function basis.

### Attributes

* `PRODUCE`, `CONSUME`: Tags used to identify output and input variable maps.
* `SKIP`: Tag indicating a function should be skipped.
* `CONTRIBUTION`, `POSITIVE`, `NEGATIVE`: Track if a function positively or negatively impacts the goals of the justification.

### Structure

Each function's context is stored like this:

```python
{
  'function_name': {
    '_produce': { var_name: value },
    '_consume': { var_name: value },
    '_skip': { 'value': True, 'reason': '...' },
    '_contribution': {
      '_positive': [...],
      '_negative': [...]
    }
  }
}
```

### Methods

#### `get(key: str) -> Any`

Returns the first value found for a variable across all declared producers/consumers.

#### `set(key: str, value: Any)`

Sets a variable’s value for the first matching declaration found (either producer or consumer).

#### `has(func: str, key: str) -> bool`

Checks if a specific function context contains the variable (either produced or consumed).

#### `set_from_config(key: str, value: Any, decorator=CONSUME)`

Used for config initialization. Sets the first matching variable from a config file without needing the function name.

#### `set_skip(func: str, value: bool, reason: str = "Skipped by condition")`

Marks a function as skipped, optionally with a reason.

#### `set_contribution(func: str, contribution_type: str, variables: list[str])`

Marks a function’s impact on justification as positive or negative, with associated variable names.

#### `get_contributions(func: str) -> dict`

Returns both positive and negative contributions for a given function:

```python
{ '_positive': [...], '_negative': [...] }
```

#### `__repr__() -> str`

Returns a developer-friendly string showing the entire context map for debug purposes.

# Pipeline Validators & Justification Schema Validator

## Pipeline Validators

The validators ensure the logical consistency, correctness, and completeness of a pipeline's variable dependencies and execution order before running it. They operate on the pipeline engine and its runtime context.

### Common base: `BaseValidator`

* Abstract base class for all validators.
* Implements an error list `self.errors` for storing error messages.
* Implements a warning list `self.warnings` for storing warning messages.
* Subclasses **must implement** the `validate()` method which performs validation and returns errors and warnings.

### 1. `MissingVariableValidator`

**Purpose:**
Check that all variables consumed by functions in the pipeline are either produced upstream or provided explicitly in the external pipeline context (e.g., config).

**Usage:**

```python
validator = MissingVariableValidator(pipeline, runtime_context)
errors, warnings = validator.validate()
```

**Returns:**

* `errors`: List of error strings describing missing variables that are declared consumed but not produced or provided.
* `warnings`: List of warnings.

### 2. `SelfDependencyValidator`

**Purpose:**
Detect functions that both consume and produce the same variable, indicating self-dependency, which usually breaks the dependency graph.

**Usage:**

```python
validator = SelfDependencyValidator(pipeline, runtime_context)
errors, warnings = validator.validate()
```

**Returns:**

* `errors`: List of error strings describing self-dependencies and suggestions to fix them.
* `warnings`: List of warnings.

### 3. `OrderValidator`

**Purpose:**
Verify that functions execute in an order respecting variable dependencies, i.e., producers appear before consumers.

**Usage:**

```python
validator = OrderValidator(pipeline, runtime_context)
errors, warnings = validator.validate()
```

**Returns:**

* `errors`: List of errors including self-dependency errors and execution order violations.
* `warnings`: List of warnings.

### 4. `ProducedButNotConsumedValidator`

**Purpose:**
Identify variables produced by functions but never consumed downstream, highlighting potentially redundant computations.

**Usage:**

```python
validator = ProducedButNotConsumedValidator(pipeline, runtime_context)
errors, warnings = validator.validate()
```

**Returns:**

* `errors`: List of errors.
* `warnings`: List of warnings about variables produced but never consumed.

### 5. `DuplicateProducerValidator`

**Purpose:**
Ensure that each variable is produced by exactly one function to avoid ambiguity.

**Usage:**

```python
validator = DuplicateProducerValidator(pipeline, runtime_context)
errors, warnings = validator.validate()
```

**Returns:**

* `errors`: List of errors.
* `warnings`: List of warnings about variables produced by multiple functions.

## Justification Schema Validator

### `JustificationSchemaValidator`

**Purpose:**
Validate the structure and logical consistency of a justification JSON definition for building justification graphs.

**Key validation checks:**

* Presence of required top-level keys: `name`, `type`, `elements`, `relations`.
* Elements each contain `id`, `label`, `type` and have valid types among: `evidence`, `strategy`, `conclusion`, `sub-conclusion`.
* Unique element IDs.
* Relations contain valid `source` and `target` IDs referencing existing elements.

**Usage:**

```python
def mark_substep(stage: str, description: str, status: str):
    # Custom implementation to mark progress or status in visualization or logs
    pass

validator = JustificationSchemaValidator(data=json_data, mark_substep=mark_substep)
try:
    validator.validate()
except ValueError as e:
    print(f"Justification validation failed: {e}")
```

**Raises:**

* `ValueError` if the justification JSON is structurally invalid or logically inconsistent.

---

For additional framework components (e.g., context, validators, runtime), please consult generated documentation in `docs/python_docs/build/html/index.html`.
