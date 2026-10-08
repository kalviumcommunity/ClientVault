# ClientVault — Team GitHub Workflow & Engineering Standards

This document establishes our team's standard operating procedures for collaborative code development, branching, issue tracking, and peer code reviews.

---

## 1. Branching Strategy

Our team uses a **trunk-based feature branch workflow** to ensure continuous integration, minimize merge conflicts, and preserve repository stability:

- **`main` Branch:**
  - Holds releasable, production-ready code only.
  - Direct commits and pushes to `main` are strictly prohibited.
  - Changes reach `main` exclusively through peer-reviewed Pull Requests.
- **Feature Branches:**
  - All work originates from an up-to-date `main` branch.
  - Branches must follow standard prefix conventions:
    - `feature/[short-description]` (or `feat/[short-description]`) — New features or pipeline additions
    - `fix/[short-description]` — Bug fixes and error handling corrections
    - `docs/[short-description]` — Documentation updates, data dictionaries, guides
    - `refactor/[short-description]` — Code restructuring without functional changes
    - `chore/[short-description]` — Build configuration, dependencies, or maintenance
- **Branch Lifecycle:**
  - Feature branches are short-lived (typically 1–3 days).
  - Feature branches are automatically deleted once merged into `main` to prevent branch clutter.

---

## 2. Commit Message Conventions

We adhere to the **Conventional Commits** specification to enable automated changelog generation, improve traceability, and provide clear historical context for every modification.

### Format
```text
[type]: [short imperative description]

[optional detailed body explaining context and rationale]
```

### Commit Types
- **`feat`**: Introduces a new capability, endpoint, or pipeline stage.
- **`fix`**: Resolves a bug, schema error, or defective behavior.
- **`docs`**: Updates documentation, READMEs, workflow guides, or data dictionaries.
- **`refactor`**: Reorganizes code without altering observable behavior.
- **`test`**: Adds or updates automated test coverage.
- **`chore`**: Maintenance tasks, dependency updates, or environment adjustments.

### Rationale
- Enables automated release notes and changelog generation.
- Communicates the developer's exact intent to reviewers during code reviews.
- Simplifies rollbacks and `git bisect` debugging.

---

## 3. Pull Request (PR) & Code Review Process

Pull Requests are the quality gate where proposed changes are inspected, tested, and validated before integration into `main`.

- **Review Requirements:**
  - Every PR requires at least one peer review approval before merging.
  - Author cannot self-approve their own PR.
- **Review Focus Areas:**
  1. **Correctness & Logic:** Does the implementation fulfill the acceptance criteria without subtle regressions?
  2. **Data Integrity & Account Isolation:** Does the code protect client boundaries and prevent cross-account data leakage?
  3. **Clarity & Maintainability:** Is the code clean, readable, properly typed, and documented?
  4. **Test Coverage:** Are unit tests and verification steps included and passing?
  5. **Commit History:** Are commit messages descriptive, atomic, and following conventions?
- **PR Description Checklist:**
  - Clear, informative PR title.
  - Summary of the problem solved and rationale.
  - Link to corresponding GitHub issues (e.g., `Closes #4`).
  - Verification evidence / test results.

---

## 4. GitHub Issue Tracking Approach

Every unit of analytical or engineering effort begins with an issue to preserve context and accountability:

- **Issue Creation:**
  - Every feature, bug fix, or refactor begins with a GitHub issue before coding starts.
  - Titles must be action-oriented (e.g., *"Ingest customer transaction data into pipeline"*, not *"Ingestion"*).
- **Issue Components:**
  - **Why It Matters:** Business or architectural rationale.
  - **Definition of Done (DoD):** Checkable criteria required for completion.
  - **Labels:** Explicit categorization (e.g., `feature`, `data-pipeline`, `documentation`, `bug`).
  - **Assignee:** Explicit owner assigned from the data product team.
- **Issue Lifecycle:**
  - Issues are referenced in PR descriptions using GitHub closing keywords (`Closes #4` or `Fixes #4`).
  - The issue is automatically closed when the associated PR is merged into `main`.

---

## 5. Active Sprint Issues

| Issue # | Title | Label | Assignee | Status |
|:---:|:---|:---|:---|:---:|
| [#4](https://github.com/kalviumcommunity/ClientVault/issues/4) | Ingest customer transaction data into pipeline | `feature`, `data-pipeline` | @Abhinavv15 | Active |
| [#5](https://github.com/kalviumcommunity/ClientVault/issues/5) | Create data quality report for incoming datasets | `data-pipeline` | @Abhinavv15 | Active |
| [#6](https://github.com/kalviumcommunity/ClientVault/issues/6) | Document data dictionary for team reference | `documentation` | @Abhinavv15 | Active |
