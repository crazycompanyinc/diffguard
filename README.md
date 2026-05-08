# DiffGuard

DiffGuard is a semantic pull request review agent. It learns lightweight codebase conventions, compares a stated change intent with the actual diff, and generates devil's advocate review arguments with concrete evidence.

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
diffguard stats
diffguard debate --pr 42
diffguard serve --port 8000
```

GitHub PR review uses `GITHUB_TOKEN`:

```bash
export GITHUB_TOKEN=...
diffguard review --pr 42 --repo owner/repo
```

The webhook server handles GitHub `pull_request` actions `opened` and `synchronize`. Configure the webhook URL as `/webhook/github`.

## What It Learns

- Per-file summaries and extracted function/class/API route names.
- Implicit contracts such as API routes using auth checks, DB writes using transactions, and functions having error handling.
- File relations from imports and local references.

## Review Output

Reviews include:

- `verdict`: `approve`, `concern`, or `block`
- `confidence`: `0.0` to `1.0`
- `arguments`: typed findings with severity, message, and evidence
- `suggestions`: concrete next steps
