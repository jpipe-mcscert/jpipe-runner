---
status: accepted
date: 2026-10-05
decision-makers: Sébastien Mosser
---

# ADR-0004: SonarCloud as the quality gate

## Context and Problem Statement

v3 had no quality gate. CI ran `pytest`, and the only threshold was a global
`fail_under = 60` coverage floor in `pyproject.toml`. No linter ran in CI, nothing was type
checked, and no pull request showed any quality signal. The v3 review behind the rewrite
(ADR-0002) found defects that a gate would have flagged: unreachable code (`--diagram`
parsed and never read), a function that always returned `True`, f-strings missing their
`f`.

A SonarCloud project, `jpipe-mcscert_jpipe-runner`, already existed in the `jpipe-mcscert`
organisation. It was on *Automatic Analysis*, which runs without the project's own build
and so cannot import coverage. Its last analysis was on 2026-04-22, and nothing read it.
The sibling repositories already gate on SonarCloud with CI-based analysis:
`jpipe-compiler` through Maven, and `jpipe-vscode` through a dedicated `sonar.yml`
workflow (its ADR-VSC-0009).

#108 adds the local checks: `ruff`, `mypy --strict`, and `pytest` with coverage. What, on
top of those, decides whether a change is good enough to merge?

## Decision Drivers

- The verdict must be visible on the pull request, where the review happens.
- Coverage must be judged on **new code**. A global floor punishes untouched legacy code
  and says nothing about the change under review. For a rewrite, all code is new.
- Free for a public repository, with nothing to host.
- The same tool and conventions as the other jPipe repositories, so one dashboard covers
  the organisation.
- Analysis must include coverage, so it has to run in CI, after the tests.

## Considered Options

1. Local tools only: `ruff`, `mypy --strict` and a `pytest-cov` `fail_under` threshold, in
   CI.
2. SonarCloud with CI-based analysis and its quality gate, on top of the local tools.
3. SonarCloud Automatic Analysis, as configured until now.
4. Codecov for coverage, plus CodeQL for static analysis.

## Decision Outcome

Chosen option: **2, SonarCloud with CI-based analysis.**

- `sonar-project.properties` gives the project's identity and scope:
  `sonar.sources=src`, `sonar.tests=tests` and
  `sonar.python.coverage.reportPaths=coverage.xml`.
- `pytest` always writes `coverage.xml` (`--cov-report=xml` in `addopts`), with
  repository-relative paths (`relative_files = true`), so the scanner can map it to files.
- `.github/workflows/sonar.yml` runs the tests and the scan
  (`SonarSource/sonarqube-scan-action`) with `sonar.qualitygate.wait=true`, so a failing
  gate fails the check. It runs on pushes to `main` and on pull requests into `main`.
  Pull requests from forks are skipped, because they get no `SONAR_TOKEN`.
  It does **not** run on milestone branches, unlike `ci.yml` (ADR-0014): the
  organisation's SonarQube Cloud plan analyses the main branch and pull requests, and
  refuses any other branch ("Organization is not allowed to access data from non main
  branches"). This was found on the first run, from `m0-foundation`. It is a
  workflow of its own, so `ci.yml` keeps no secret in its environment and a SonarCloud
  outage cannot hide the test results.
- The global `fail_under` floor is removed. The gate's coverage-on-new-code condition
  replaces it.
- `ruff` and `mypy --strict` stay in `ci.yml` and pre-commit. They are fast, local and
  deterministic. SonarCloud adds what they lack: new-code coverage, duplication, security
  hotspots and a verdict on the pull request.

### Consequences

- Good, because each pull request shows its gate verdict and the issues in its diff.
- Good, because the thresholds apply to new code, which suits a rewrite.
- Good, because the configuration matches the sibling repositories.
- Bad, because the gate depends on an external service and a secret. An outage or an
  expired token fails the `SonarQube` check, though not `ci.yml`.
- Bad, because the tests run twice per push, once in `ci.yml` and once in `sonar.yml`.
- Neutral, because a milestone branch is analysed through its pull request, which is
  therefore opened as a draft when the milestone starts (ADR-0015).
- Bad, because some of the setup lives outside the repository. It is done once, by a
  maintainer:
  - turn off *Automatic Analysis* for the project (CI-based analysis is refused while it
    is on);
  - add the `SONAR_TOKEN` repository secret;
  - make sure the SonarCloud GitHub App is installed on the repository, so it can
    decorate pull requests;
  - optionally, make the `SonarQube` check required on `main`.

### Confirmation

- The `SonarQube` check appears on the milestone pull requests and passes.
- The SonarCloud project shows an analysis per push, with coverage greater than zero.

## Pros and Cons of the Options

### 1. Local tools only

- Good, because it has no external dependency and no secret.
- Bad, because a global coverage floor does not judge the change under review.
- Bad, because the pull request shows only pass or fail, with no issues attached to its
  diff.

### 3. Automatic Analysis

- Good, because it needs no CI setup at all.
- Bad, because it cannot import coverage, so the gate cannot check it.
- Bad, because nobody looked at it, as its last analysis on 2026-04-22 shows.

### 4. Codecov and CodeQL

- Good, because both are free for public repositories, and CodeQL is native to GitHub.
- Bad, because that makes two services to configure where one would do, and neither
  combines its results into a single gate.
- Bad, because it would differ from the rest of the jPipe organisation.

## More Information

- #108 adds the local tools. #109 implements this decision.
- `jpipe-vscode`'s `sonar.yml` and its ADR-VSC-0009 are the model for the workflow.
