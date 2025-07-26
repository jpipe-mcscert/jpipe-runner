# jPipe Runner — Usage Guide

This document explains how to execute the **jPipe Runner** CLI with different parameters, along with practical examples.

---

## Command-Line Interface (CLI) Overview

```bash
jpipe-runner [OPTIONS] jd_file
```

* `jd_file` — Path to the justification `.jd.json` file to execute.

## Important

> **You must specify both the justification `.jd.json` file *and* at least one Python library file (`--library`) when executing `jpipe-runner`.**

---

## Available Parameters

| Parameter       | Short | Description                                                                                                     |
|-----------------|-------|-----------------------------------------------------------------------------------------------------------------|
| `--variable`    | `-v`  | Define variables as `NAME:VALUE`. Can be used multiple times to inject variables into the workflow.             |
| `--library`     | `-l`  | Path(s) or pattern(s) to additional Python libraries to load before execution. Can be specified multiple times. |
| `--diagram`     | `-d`  | Wildcard pattern to filter and select specific diagrams to generate (default: `"*"` for all).                   |
| `--output`      | `-o`  | Output file path to save the generated diagram image. The format is inferred from the file extension.           |
| `--dry-run`     |       | Simulate the execution without performing any justifications or outputs (checks workflow validity).             |
| `--verbose`     | `-V`  | Enable verbose/debug logging to help diagnose issues.                                                           |
| `--config-file` |       | Path to a YAML configuration file that can specify variables, libraries, diagrams, and other settings.          |
| `--gui`         |       | Launch a graphical interface (Tkinter-based) to visualize and interact with workflow execution steps.           |

---

## Supported Output Image Formats

When specifying the `--output` option, you can choose any of the following formats by file extension<sup>1</sup>:

`canon`, `cmap`, `cmapx`, `cmapx_np`, `dia`, `dot`, `fig`, `gd`, `gd2`, `gif`, `hpgl`,
`imap`, `imap_np`, `ismap`, `jpe`, `jpeg`, `jpg`, `mif`, `mp`, `pcl`, `pdf`, `pic`,
`plain`, `plain-ext`, `png`, `ps`, `ps2`, `svg`, `svgz`, `vml`, `vmlz`, `vrml`, `vtx`,
`wbmp`, `xdot`, `xlib`

<sup>1</sup> The quality and features of the output may vary depending on the chosen format.

---

## Examples


### Basic Execution

```bash
jpipe-runner -l './libraries/notebook.py' ./models/02_quality_full.jd.json
```

Executes the workflow specified in the `.jd.json` with the corresponding library `.py` file without extra options.

---

### Defining Variables

```bash
jpipe-runner -v notebook:notebook.ipynb -l './libraries/notebook.py' ./models/02_quality_full.jd.json
```

Injects a variable named `notebook` with value `notebook.ipynb` into the workflow.

> ### ⚠️ Important Notes on Variable Formatting
>
> When passing **lists**, **booleans**, or **complex values** using the `--variable` option, the values must be specified in a format that can be correctly parsed by the runner (using Python-style or JSON-compatible syntax).
> 
> #### ✅ Correct Formatting
> 
> * **Lists** (must be quoted):
> 
>   ```bash
>   --variable values_path="['dev-values.yaml', 'prod-values.yaml']"
>   ```
> 
> * **Booleans** (use capital `True`/`False` — Python style, no lowercase):
> 
>   ```bash
>   --variable enable_checks:True
>   ```
> 
> #### ❌ Common Mistakes
> 
> * ❌ Unquoted lists are invalid and will be interpreted as plain strings:
> 
>   ```bash
>   --variable values_path=[dev-values.yaml]  # ← Invalid syntax
>   ```
> 
>     This results in:
>     
>     ```python
>     type(values_path)  # str
>     ```
>   
>     Instead of:
> 
>     ```python
>     type(values_path)  # list[str]
>     ```
> 
> * ❌ Lowercase booleans (`true`, `false`) will be treated as **strings**, not actual booleans:
> 
>   ```bash
>   --variable enable_checks:true  # ← Interpreted as string 'true'
>   ```
> 
>   This results in:
> 
>   ```python
>   type(enable_checks)  # str
>   ```
> 
>   Instead of:
> 
>   ```python
>   type(enable_checks)  # bool
>   ```
> 
> ### ✅ Correct Example (Mixed Types)
> 
> ```bash
> jpipe-runner \
>   -v helm_chart_path:/charts/myapp \
>   -v values_path="['/charts/myapp/dev-values.yaml']" \
>   -v enable_lint:True \
>   -v dry_run:False \
>   -l './libraries/deploy.py' \
>   ./models/deployment.jd.json
> ```
> 
> ### Summary
> 
> | Type    | Correct Example                | Incorrect Example                                      |
> |---------|--------------------------------|--------------------------------------------------------|
> | List    | `"['a.yaml', 'b.yaml']"`       | `[a.yaml, b.yaml]` (missing quotes)                    |
> | Boolean | `True` / `False` (capitalized) | `true` / `false` (lowercase)                           |
> | Dict    | `"{'key': 'value'}"`           | `{key: value}` (missing quotes)                        |
> | String  | `"some_string"` or `plain_str` | - (strings usually work unquoted unless special chars) |
> | Number  | `123`, `3.14`                  | - (Quoted or unquoted numbers parse as int/float)      |
> | None    | `None` (capitalized)           | `null`, `none`, `NULL` (lowercase or variants)         |
> 
> 
> ### Example with List
> 
> ```bash
> jpipe-runner \
>   -v helm_chart_path:/charts/myapp \
>   -v values_path="['/charts/myapp/dev-values.yaml']" \
>   -l './libraries/deploy.py' \
>   ./models/deployment.jd.json
> ```
> 
> This ensures `values_path` is passed as a `list[str]`, not a plain string.

---

### Generate Diagram Image Output

```bash
jpipe-runner -l './libraries/notebook.py' -v notebook:notebook.ipynb --output ./test.png ./models/02_quality_full.jd.json
```

Runs the workflow and outputs the execution diagram as a PNG image at `./test.png`.

---

### Enable Verbose Logging

```bash
jpipe-runner -l './libraries/notebook.py' -v notebook:notebook.ipynb --output ./test.png --verbose ./models/02_quality_full.jd.json
```

Prints detailed debug information during execution to help troubleshoot.

---

### Dry Run (Validate Without Execution)

```bash
jpipe-runner --dry-run -l './libraries/notebook.py' ./models/02_quality_full.jd.json
```

Validates the workflow without performing actual justification steps or generating outputs.

---

### Use a YAML Configuration File

```bash
jpipe-runner -l './libraries/notebook.py' --config-file ./config/settings.yaml ./models/02_quality_full.jd.json
```

Loads variables, libraries, and other settings from a YAML config file instead of specifying on the command line.

---

### Launch GUI Visualizer

```bash
jpipe-runner --gui -l './libraries/notebook.py' ./models/02_quality_full.jd.json
```

Runs the workflow with a Tkinter-based GUI that shows execution steps interactively.

---

## Notes

* Multiple `--variable` and `--library` options can be specified by repeating the flags.
* The diagram output format depends on the file extension specified in `--output`.
* Use `--verbose` to get detailed logs, especially useful for debugging complex workflows.
* The `--gui` mode is helpful for visually inspecting the flow and step execution.
