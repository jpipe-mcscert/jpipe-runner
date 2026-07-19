# jPipe Runner — GitHub Action

Run your jPipe justification diagrams in CI. On every pull request the Action executes the
justification, posts the result as a PR comment, and uploads the generated diagram as a
build artifact.

**What you get on each run**

- A **PR comment** saying whether the justification passed or failed (with the runner's
  error output, cleaned up, when it fails).
- The generated **diagram as an artifact**, downloadable from the workflow run.
- Optionally, the diagram **rendered inline** in the PR comment (see
  [How do I show the diagram inline?](#how-do-i-show-the-diagram-inline-in-the-pr-comment)).
- An **exit code** you can branch on — the step fails if the justification fails.

---

## Quick start

Add `.github/workflows/jpipe.yml`:

```yaml
name: Run jPipe Justification

on:
  pull_request:

permissions:
  pull-requests: write   # to post the result comment

jobs:
  justify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5

      - name: Run jPipe Runner
        uses: jpipe-mcscert/jpipe-runner@v3.5.3
        with:
          jd_file: "path/to/justification.jd.json"
          library: "my_library.py"
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

That's the whole minimum: a justification file, the Python library implementing it, and a
token so the Action can comment on the PR.

---

## Common recipes

### Inject variables and load several libraries

Both inputs are newline-separated lists.

```yaml
with:
  jd_file: "justification.jd.json"
  library: |
    analysis.py
    metrics.py
  variable: |
    user_name:Alice
    threshold:42
```

### Show the diagram inline in the PR comment

This commits the rendered image to a branch so GitHub can display it — see the
[FAQ](#why-does-inline-embedding-need-a-branch) for why. It needs `contents: write`.

```yaml
permissions:
  contents: write        # only needed for embed_image
  pull-requests: write

# ...
with:
  jd_file: "justification.jd.json"
  library: "my_library.py"
  embed_image: true
  image_branch: "jpipe-runner-diagrams"   # created automatically if absent
  github-token: ${{ secrets.GITHUB_TOKEN }}
```

### Pin the runner version

`version` selects which jPipe Runner is installed. It is a **git ref** — a tag, branch, or
commit SHA. Pin both it and the Action itself for reproducible builds:

```yaml
uses: jpipe-mcscert/jpipe-runner@v3.5.3   # pins the Action
with:
  version: "v3.5.3"                       # pins the runner it installs
```

### Choose a different Python

The Action installs Python 3.11 by default. To run against your own interpreter:

```yaml
- uses: actions/setup-python@v6
  id: setup-python
  with:
    python-version: "3.12"

- uses: jpipe-mcscert/jpipe-runner@v3.5.3
  with:
    jd_file: "justification.jd.json"
    library: "my_library.py"
    python_exec_path: ${{ steps.setup-python.outputs.python-path }}
    python_path: |
      src
      lib
```

### Run in a subdirectory, or render a different format

```yaml
with:
  working_directory: "analysis/"     # all paths below are relative to this
  jd_file: "justification.jd.json"
  library: "my_library.py"
  format: "png"                      # dot, gif, jpeg, jpg, pdf, png, svg
  diagram: "MyDiagram*"              # which diagram(s) to render; default "*"
```

### Use the outputs

```yaml
- uses: jpipe-mcscert/jpipe-runner@v3.5.3
  id: jpipe
  continue-on-error: true
  with:
    jd_file: "justification.jd.json"
    library: "my_library.py"

- name: React to the result
  run: echo "Runner exited with ${{ steps.jpipe.outputs.result }}"
```

---

## FAQ

### What permissions do I actually need?

Only what you use:

| Permission | When | Why |
|---|---|---|
| `pull-requests: write` | To post the PR comment | The Action comments on the PR |
| `contents: write` | **Only** if `embed_image: true` | It commits the image to a branch |

Uploading the diagram artifact needs **no** special permission. If you are not embedding
images, `contents: write` is unnecessary — leave it out.

### Why does inline embedding need a branch?

Because GitHub renders markdown images through its **camo** proxy, which fetches the image
URL **anonymously**. The image therefore has to live somewhere reachable without a login.
Committing it to a branch produces a `raw.githubusercontent.com` URL that satisfies this.

This is also why the artifact **cannot** be embedded: artifact URLs require the viewer to be
signed in, so `![](artifact-url)` would render as a broken image. The artifact is always
offered as a download link instead. Inline `<svg>` and `data:` URIs don't work either —
GitHub sanitises both out of comments.

### How do I show the diagram inline in the PR comment?

Set `embed_image: true`, grant `contents: write`, and pass `github-token`. The image is
committed to `image_branch` (default `jpipe-runner-diagrams`, created automatically) under a
folder named `<your-repo>_<image_path>`. Point `image_repo` elsewhere if you'd rather not
store images in the same repository.

### Does inline embedding work in private repositories?

It's **best-effort**. A private repo has no anonymously-reachable URL, so the Action falls
back to a signed contents-API URL that carries a **time-limited token**. It renders because
camo fetches and caches the image when the comment is first displayed — but if camo ever
re-fetches after that token expires, the inline image can break. The artifact download link
in the comment always keeps working.

If the signed URL cannot be resolved at all, the Action posts the comment with the download
link and a warning instead of embedding a broken image.

### What is the artifact, and what format is it in?

One file — the rendered diagram, named `<diagram>_<commit-sha>.<format>` so runs don't
overwrite each other. It is uploaded **unzipped**, so downloading it gives you the image
directly rather than a `.zip` to extract.

> Requires an Actions runner ≥ 2.327.1 (Node 24). GitHub-hosted runners are fine; update
> self-hosted runners if you use them.

### The justification failed — where do I look?

The PR comment includes the runner's output in a collapsible *Runner Output* section, with
the ASCII banner and summary table stripped so only the error text remains. Full, unedited
output is always in the workflow logs under the *Run jPipe Runner* group.

The step also fails the job on a non-zero exit. Use `continue-on-error: true` plus the
`result` output if you'd rather handle it yourself.

### Which Python is used?

Python 3.11, installed by the Action. Override it with `python_exec_path` (see the recipe
above). Use `python_path` to add folders to the module search path — it does **not** select
an interpreter.

### Can I use it outside a pull request?

Yes. The justification runs and the artifact uploads normally on any trigger; the comment
step simply skips itself when there's no PR context.

---

## Reference

### Inputs

| Input | Description | Required | Default |
|---|---|---|---|
| `jd_file` | Path to the justification `.jd.json` file | **Yes** | — |
| `library` | Python libraries to load, one per line | **Yes** | — |
| `variable` | Variables as `NAME:VALUE`, one per line | No | — |
| `config-file` | Path to a jPipe Runner config file (YAML) | No | — |
| `diagram` | Diagram name pattern or wildcard | No | `*` |
| `format` | `dot`, `gif`, `jpeg`, `jpg`, `pdf`, `png`, `svg` | No | `svg` |
| `dry_run` | Validate without executing the justification | No | `false` |
| `python_exec_path` | Python interpreter to use | No | *(built-in 3.11)* |
| `python_path` | Extra module search folders, one per line | No | — |
| `working_directory` | Directory to run in | No | `.` |
| `version` | jPipe Runner git ref to install (tag, branch, or SHA) | No | `main` |
| `embed_image` | Render the diagram inline in the PR comment | No | `false` |
| `image_branch` | Branch the image is committed to | No | `jpipe-runner-diagrams` |
| `image_repo` | Target repo `owner/repo` for the image | No | *(current repo)* |
| `image_path` | Folder for the image inside the branch | No | `diagrams/` |
| `image_commit_message` | Commit message for the image | No | `Add generated diagram from jPipe Runner` |
| `github-token` | Token used to comment and commit | No¹ | — |
| `github-readonly-token` | Read-only token used only to build the image URL | No | — |

¹ Required in practice to post the PR comment, and required when `embed_image: true`.
`${{ secrets.GITHUB_TOKEN }}` is normally the right value.

### Outputs

| Output | Description |
|---|---|
| `result` | Exit code of the jPipe Runner execution (`0` = success) |
| `diagram_path` | Path to the generated diagram file |
| `pr_comment_id` | ID of the posted PR comment (empty outside a PR) |

### Version pinning

`uses:` pins the **Action**; the `version` input pins the **runner** it installs. Pinning
both is recommended — leaving `version` at its `main` default means you pick up runner
changes as they land.
