# DiffGuard

DiffGuard v2.0 is a semantic pull request review agent. It learns codebase conventions, builds a knowledge graph, compares stated intent with the actual diff, and generates production-grade review evidence with concrete fixes.

## Install

```bash
pip install -e ".[dev]"
diffguard --help
```

## Usage

```bash
diffguard init
diffguard learn .
git diff main...HEAD > change.diff
diffguard review --diff change.diff --intent "fix typo in account page"
diffguard review-v2 --diff change.diff --intent "fix typo in account page" --agent Agent-Alpha
diffguard stats
diffguard debate --pr 42
diffguard serve --port 8000
```

Run the included v2 demo:

```bash
diffguard review-v2 --diff demo/v2_demo.diff --intent "refactor user lookup" --agent Agent-Alpha
```

GitHub PR review uses `GITHUB_TOKEN`:

```bash
export GITHUB_TOKEN=...
diffguard review --pr 42 --repo owner/repo
```

The webhook server handles GitHub `pull_request` actions `opened` and `synchronize`. Configure the webhook URL as `/webhook/github`.

## v2.0 Capabilities

- Multi-language structural analysis for Python, JavaScript, TypeScript, Go, Java, Ruby, and Rust.
- Semantic diff classification: renames, signature changes, return type changes, symbol additions/removals, documentation-only edits, and business logic changes.
- Knowledge graph impact analysis across learned files, symbols, imports, and test relations.
- Historical learning from stored PR reviews and cross-PR interaction warnings.
- Agent-specific review policies such as stricter auth review for `Agent-Alpha`.
- Security audit mode for SQL injection, XSS, auth bypass, data leakage, and sensitive logging.
- Performance impact checks for nested loops, query-in-loop patterns, and blocking work.
- Auto-fix snippets, reviewer assignment, PR quality scoring, and simulated review conversations.

## Review Output

Reviews include:

- `verdict`: `approve`, `concern`, or `block`
- `confidence`: `0.0` to `1.0`
- `arguments`: typed findings with severity, message, and evidence
- `suggestions`: concrete next steps

`review-v2` includes all of the above plus `semantic_changes`, `graph_impacts`, `historical_matches`, `cross_pr_impacts`, `agent_findings`, `auto_fixes`, `reviewer_recommendations`, `quality_score`, `conversation`, `security_findings`, and `performance_findings`.
