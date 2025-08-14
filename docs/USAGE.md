# jPipe Runner — Usage Guide

This document explains how to execute the **jPipe Runner** CLI with different parameters, along with practical examples.

## Command-Line Interface (CLI) Overview

```bash
jpipe-runner [OPTIONS] jd_file
```

* `jd_file` — Path to the justification `.jd.json` file to execute.

## Important

> **You must specify both the justification `.jd.json` file *and* at least one Python library file (`--library`) when
executing `jpipe-runner`.**

## Available Parameters

| Parameter       | Short | Description                                                                                                     |
|-----------------|-------|-----------------------------------------------------------------------------------------------------------------|
| `--variable`    | `-v`  | Define variables as `NAME:VALUE`. Can be used multiple times to inject variables into the justification.        |
| `--library`     | `-l`  | Path(s) or pattern(s) to additional Python libraries to load before execution. Can be specified multiple times. |
| `--diagram`     | `-d`  | Wildcard pattern to filter and select specific diagrams to generate (default: `"*"` for all).                   |
| `--format`      | `-f`  | Format of the output diagram image.                                                                             |
| `--output-path` | `-o`  | Output file path to save the generated diagram image.                                                           |
| `--dry-run`     |       | Simulate the execution without performing any justifications or outputs (checks justification validity).        |
| `--verbose`     | `-V`  | Enable verbose/debug logging to help diagnose issues.                                                           |
| `--config-file` |       | Path to a YAML configuration file that can specify variables, libraries, diagrams, and other settings.          |
| `--gui`         |       | Launch a graphical interface (Tkinter-based) to visualize and interact with workflow execution steps.           |

## Supported Output Image Formats

When specifying the `--output` option, you can choose any of the following formats by file extension<sup>1</sup>:

`dot`, `gif`, `jpeg`, `jpg`, `pdf`, `png`, `svg`

<sup>1</sup> The quality and features of the output may vary depending on the chosen format.

## Examples

### Basic Execution

```bash
jpipe-runner -l './libraries/notebook.py' ./models/02_quality_full.jd.json
```

Executes the justification specified in the `.jd.json` with the corresponding library `.py` file without extra options.

### Defining Variables

```bash
jpipe-runner -v notebook:notebook.ipynb -l './libraries/notebook.py' ./models/02_quality_full.jd.json
```

Injects a variable named `notebook` with value `notebook.ipynb` into the workflow.

> ### ⚠️ Important Notes on Variable Formatting
>
> The runner now supports parsing variables in both **JSON** and **Python literal** syntax, including booleans (`true`/
`false` or `True`/`False`), `null`/`None`, numbers, lists, dicts, and nested structures.
>
> #### ✅ Examples of Supported Variable Formats
>
> ```bash
> poetry run python -m jpipe_runner \
> --variable 'input_data:[1,2,3,null,4,5]' \
> --variable 'steps:[{"name":"step1","enabled":true,"retries":"3"},{"name":"step2","enabled":"false","retries":0}]' \
> --variable 'metadata:{"version":"1.0","tags":["alpha","beta","42",null],"params":{"threshold":"0.75","max_items":"100","debug_mode":"True"}}' \
> --variable 'settings:{"numbers":[1,2,3],"options":{"key":"value","flag":true}}' \
> --variable 'nested_list:[{"a":1},{"b":2}]' \
> -l ./tests/e2e/resources/complex_success/data_pipeline.py \
> tests/e2e/resources/complex_success/data_pipeline.json
> ```
>
> - **Booleans**: Accepts both `true`/`false` (JSON) and `True`/`False` (Python).
> - **Null/None**: Accepts `null` (JSON) and `None` (Python).
> - **Numbers**: Integers and floats are parsed automatically.
> - **Lists/Dicts**: Both JSON (`[1,2,3]`, `{"a":1}`) and Python (`[1, 2, 3]`, `{'a': 1}`) styles are supported.
> - **Strings**: Quoted or unquoted, as long as they do not conflict with other types.
>
> #### ❌ Common Mistakes
>
> * Unmatched brackets or braces will cause parsing errors.
> * For complex/nested values, always wrap the entire value in single quotes to avoid shell interpretation issues.
>
> #### 📝 Summary Table
>
> | Type    | Example (JSON/Python)                | Resulting Python Type      |
> |---------|--------------------------------------|---------------------------|
> | List    | `[1,2,3]` or `[1, 2, 3]`             | `list[int]`               |
> | Boolean | `true`/`false` or `True`/`False`     | `bool`                    |
> | Dict    | `{"a":1}` or `{'a': 1}`              | `dict`                    |
> | String  | `"abc"` or `abc`                     | `str`                     |
> | Number  | `42`, `3.14`                         | `int`/`float`             |
> | None    | `null` or `None`                     | `NoneType`                |
>
> The runner will automatically convert these values to the correct Python types for use in your workflow.

### Generate Diagram Image Output

```bash
jpipe-runner -l './libraries/notebook.py' -v notebook:notebook.ipynb --format 'png' --output-path ./my_diagram_output_folder/ ./models/02_quality_full.jd.json
```

Runs the justification and outputs the execution diagram as a PNG image at
`./my_diagram_output_folder/<name_of_the_justification>.png`.

### Enable Verbose Logging

```bash
jpipe-runner -l './libraries/notebook.py' -v notebook:notebook.ipynb --verbose ./models/02_quality_full.jd.json
```

Prints detailed debug information during execution to help troubleshoot.

### Dry Run (Validate Without Execution)

```bash
jpipe-runner --dry-run -l './libraries/notebook.py' ./models/02_quality_full.jd.json
```

Validates the justification without performing actual justification steps or generating outputs.

### Use a YAML Configuration File

```bash
jpipe-runner -l './libraries/notebook.py' --config-file ./config/settings.yaml ./models/02_quality_full.jd.json
```

Loads variables, libraries, and other settings from a YAML config file instead of specifying on the command line.

### Launch GUI Visualizer

```bash
jpipe-runner --gui -l './libraries/notebook.py' ./models/02_quality_full.jd.json
```

Runs the justification with a Tkinter-based GUI that shows execution steps interactively.

## Notes

* Multiple `--variable` and `--library` options can be specified by repeating the flags.
* The `--output-path` must be a valid directory where the output image can be saved.
* The diagram output format depends on the file extension specified in `--format`.
* Use `--verbose` to get detailed logs, especially useful for debugging complex justification.
* The `--gui` mode is helpful for visually inspecting the flow and step execution.
