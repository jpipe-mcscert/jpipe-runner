# Action: jPipe Runner GitHub Action

### Overview

This GitHub Action executes jPipe Runner to generate justification diagrams from `.jd.json` files.
It supports variable injection, configuration files, library imports, multiple output formats, and optional embedding
of diagrams in PR comments or uploading them as artifacts.

**When embedding images in PR comments, the generated diagrams must be stored in a Git repository in a specified branch.
**

The action is implemented as a composite GitHub Action with multiple Bash scripts handling installation, execution,
and artifact management.

### Required Inputs

| Input     | Description                                                         | Required | Default |
|-----------|---------------------------------------------------------------------|----------|---------|
| `jd_file` | Path to the justification `.jd.json` file                           | Yes      | --      |
| `library` | Specify one or more Python libraries to load, separated by newlines | Yes      | --      |

#### Conditional Required Inputs

| Input          | Description                                         | Required If                         | Default |
|----------------|-----------------------------------------------------|-------------------------------------|---------|
| `embed_image`  | Embed diagram in PR comment (`true`) or upload only | No                                  | `false` |
| `github-token` | GitHub token to authenticate                        | Required if `embed_image` is `true` | --      |

### Optional Inputs

| Input                  | Description                                                    | Default                                   |
|------------------------|----------------------------------------------------------------|-------------------------------------------|
| `variable`             | Define variables in `NAME:VALUE` format, separated by newlines | --                                        |
| `config-file`          | Path to jPipe Runner configuration file (YAML)                 | --                                        |
| `diagram`              | Specify diagram pattern or wildcard                            | `*`                                       |
| `format`               | Output format for the diagram (`dot`, `gif`, `jpeg`, etc.)     | `svg`                                     |
| `dry_run`              | Perform a dry run without executing justifications             | `false`                                   |
| `python_path`          | Path to Python interpreter                                     | (defaults to system Python)               |
| `working_directory`    | Working directory to run jPipe Runner                          | `.`                                       |
| `version`              | jPipe Runner version to use (e.g., `0.0.1`)                    | `main`                                    |
| `image_branch`         | Branch name to commit the diagram                              | `jpipe-runner-diagrams`                   |
| `image_repo`           | Target repo for diagram commit (`owner/repo`)                  | Defaults to current repo                  |
| `image_path`           | Path to store the image in branch                              | `diagrams/`                               |
| `image_commit_message` | Commit message for generated diagram                           | `Add generated diagram from jPipe Runner` |

**Notes:**

- If `embed_image` is set to `true`, `github-token` must be provided.

## Configuration & Permissions

To ensure the **jPipe Runner** GitHub Action works correctly, you need to configure the repository and workflow
permissions appropriately.

### 1. Workflow File Setup

In your repository, create or update a workflow file (e.g., `.github/workflows/jpipe.yml`) to include the **jPipe Runner
** Action. Here’s a minimal example:

```yaml
name: Run jPipe Justification

on:
  pull_request:
    branches:
      - main
  workflow_dispatch:

permissions:
  contents: write        # Required to push diagram images to repository
  pull-requests: write   # Required to post comments on PRs

jobs:
  run-jpipe:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Run jPipe Runner
        uses: your-org/jpipe-runner-action@main
        with:
          jd_file: "path/to/justification.jd.json"
          library: |
            mylib1
            mylib2
          embed_image: true
          image_branch: "my_diagram_branch"
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

### 2. Required Repository Permissions

The Action needs the following **permissions** to execute properly:

| Permission             | Level   | Reason                                                                   |
|------------------------|---------|--------------------------------------------------------------------------|
| `contents`             | `write` | To commit diagram images to a branch and upload artifacts                |
| `pull-requests`        | `write` | To post comments with diagram results in Pull Requests                   |
| `secrets.GITHUB_TOKEN` | access  | Required for authentication when committing files or posting PR comments |

> **Note:** These permissions are configured in the workflow file under `permissions`. Using
`${{ secrets.GITHUB_TOKEN }}` ensures secure access.

### 3. Optional Configuration

* **Image Commit Branch**: If you want diagrams committed to a specific branch, set the `image_branch` input. Make sure
  the branch exists in your repository.
* **Custom Repository**: To push diagrams to a different repository, set `image_repo` input with `owner/repo`.
* **Python Environment**: The Action defaults to Python 3.11. Use `python_path` if you need a custom Python interpreter.

### 4. Secrets and Tokens

* **GITHUB\_TOKEN**: Automatically provided by GitHub for each workflow run; used for authentication.
* **Additional Secrets**: If you need access to private repositories or external resources, create corresponding secrets
  in your repository settings.

## Scripts

### Details: Output Log Cleaning in `build_comment.sh`

To generate a clean output log for the PR comment, the script performs two key cleaning steps:

1. **Removes the first 9 lines** of the runner output, which correspond to the initial ASCII warning banner and header.
2. **Removes the jPipeRunner resume section** (from the jPipeRunner ASCII logo to the end of the output).

> **Important:**  
> If the ASCII banner or the jPipeRunner logo changes (e.g., number of lines, formatting), you must update the script
> accordingly:
> - Adjust the `tail -n +10` command to match the new banner length.
> - Update the `sed` pattern that detects the start of the jPipeRunner ASCII logo.

This ensures the PR comment only displays relevant error information and not extraneous banners or summaries.
