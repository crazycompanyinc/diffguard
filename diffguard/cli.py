"""Click command line interface for DiffGuard."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import click
import httpx

from diffguard.core.db import DiffGuardDB
from diffguard.debater.debater import PRDebater
from diffguard.learner.context_learner import CodebaseContextLearner
from diffguard.server.app import create_app
from diffguard.v2.review import V2ReviewEngine


@click.group()
def main() -> None:
    """Semantic PR review agent that plays devil's advocate."""


@main.command()
def init() -> None:
    """Create .diffguard configuration in the current repo."""
    config_dir = Path(".diffguard")
    config_dir.mkdir(exist_ok=True)
    config_file = config_dir / "config.json"
    if not config_file.exists():
        config_file.write_text(json.dumps({"db": "diffguard.sqlite3"}, indent=2), encoding="utf-8")
    DiffGuardDB(config_dir / "diffguard.sqlite3").close()
    click.secho("DiffGuard initialized in .diffguard/", fg="green")


@main.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, path_type=Path))
def learn(path: Path) -> None:
    """Scan a codebase and build a context map."""
    db = DiffGuardDB()
    stats = CodebaseContextLearner(db).learn(path)
    click.secho(f"Learned {stats['files']} files, {stats['relations']} relations, {stats['contracts']} contracts.", fg="green")


@main.command()
@click.option("--diff", "diff_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--intent", default="", help="Stated PR title or description.")
@click.option("--pr", type=int, help="GitHub PR number.")
@click.option("--repo", help="GitHub repo as owner/name.")
def review(diff_file: Path | None, intent: str, pr: int | None, repo: str | None) -> None:
    """Review a local diff file or GitHub PR."""
    if pr is not None:
        if not repo:
            raise click.ClickException("--repo is required with --pr")
        diff_text, intent = fetch_github_pr(repo, pr)
        result = PRDebater(DiffGuardDB()).review_diff(diff_text, intent, pr_number=pr, repo=repo)
    else:
        if not diff_file or not intent:
            raise click.ClickException("--diff and --intent are required for local review")
        result = PRDebater(DiffGuardDB()).review_diff(diff_file.read_text(encoding="utf-8"), intent)
    print_result(result.to_dict())


@main.command("review-v2")
@click.option("--diff", "diff_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--intent", default="", help="Stated PR title or description.")
@click.option("--pr", type=int, help="GitHub PR number.")
@click.option("--repo", help="GitHub repo as owner/name.")
@click.option("--agent", help="Authoring agent name for agent-specific policies.")
def review_v2(diff_file: Path | None, intent: str, pr: int | None, repo: str | None, agent: str | None) -> None:
    """Run the full DiffGuard v2 production review."""
    if pr is not None:
        if not repo:
            raise click.ClickException("--repo is required with --pr")
        diff_text, intent = fetch_github_pr(repo, pr)
        result = V2ReviewEngine(DiffGuardDB()).review_diff(diff_text, intent, pr_number=pr, repo=repo, agent=agent)
    else:
        if not diff_file or not intent:
            raise click.ClickException("--diff and --intent are required for local review")
        result = V2ReviewEngine(DiffGuardDB()).review_diff(diff_file.read_text(encoding="utf-8"), intent, agent=agent)
    print_v2_result(result.to_dict())


@main.command()
@click.option("--port", default=8000, show_default=True, type=int)
def serve(port: int) -> None:
    """Start webhook server for GitHub events."""
    import uvicorn

    click.secho(f"Serving DiffGuard on http://127.0.0.1:{port}", fg="green")
    uvicorn.run(create_app(), host="127.0.0.1", port=port)


@main.command()
def stats() -> None:
    """Show what DiffGuard has learned."""
    data = DiffGuardDB().stats()
    for key, value in data.items():
        click.echo(f"{key}: {value}")


@main.command()
@click.option("--pr", type=int, required=True)
@click.option("--repo", help="GitHub repo as owner/name.")
def debate(pr: int, repo: str | None) -> None:
    """Enter a deterministic debate mode about a PR."""
    if repo:
        diff_text, intent = fetch_github_pr(repo, pr)
    else:
        diff_text = _git_diff_or_empty()
        intent = f"Local PR {pr}"
    transcript = PRDebater(DiffGuardDB()).debate(diff_text, intent)
    for turn in transcript:
        color = "red" if turn["speaker"] == "DiffGuard" else "cyan"
        click.secho(f"{turn['speaker']}: ", fg=color, nl=False)
        click.echo(turn["message"])


def fetch_github_pr(repo: str, pr: int) -> tuple[str, str]:
    token = os.getenv("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with httpx.Client(timeout=20.0) as client:
        pr_response = client.get(f"https://api.github.com/repos/{repo}/pulls/{pr}", headers=headers)
        pr_response.raise_for_status()
        payload = pr_response.json()
        diff_response = client.get(payload["diff_url"], headers=headers)
        diff_response.raise_for_status()
    intent = f"{payload.get('title', '')}\n\n{payload.get('body') or ''}"
    return diff_response.text, intent


def print_result(result: dict[str, object]) -> None:
    verdict = str(result["verdict"])
    color = "green" if verdict == "approve" else "yellow" if verdict == "concern" else "red"
    click.secho(f"Verdict: {verdict}  Confidence: {result['confidence']}", fg=color, bold=True)
    for argument in result.get("arguments", []):  # type: ignore[assignment]
        click.secho(f"[{argument['severity']}] {argument['type']}", fg=color)
        click.echo(f"  {argument['message']}")
        click.echo(f"  evidence: {json.dumps(argument['evidence'], sort_keys=True)}")
    click.secho("Suggestions:", fg="blue")
    for suggestion in result.get("suggestions", []):  # type: ignore[assignment]
        click.echo(f"  - {suggestion}")


def print_v2_result(result: dict[str, object]) -> None:
    base = result["base_review"]  # type: ignore[index]
    print_result(base)  # type: ignore[arg-type]
    score = result["quality_score"]  # type: ignore[index]
    click.secho(f"Quality: {score['overall']} (tests {score['test_coverage']}, conventions {score['conventions']})", fg="magenta")  # type: ignore[index]
    for section in ("semantic_changes", "security_findings", "performance_findings", "graph_impacts", "cross_pr_impacts", "agent_findings"):
        items = result.get(section, [])  # type: ignore[assignment]
        if items:
            click.secho(section.replace("_", " ").title() + ":", fg="blue")
            for item in items[:6]:
                click.echo(f"  - {json.dumps(item, sort_keys=True)}")
    reviewers = result.get("reviewer_recommendations", [])  # type: ignore[assignment]
    if reviewers:
        click.secho("Reviewer Recommendations:", fg="blue")
        for reviewer in reviewers:
            click.echo(f"  - {reviewer['reviewer']} ({reviewer['confidence']}): {reviewer['reason']}")
    fixes = result.get("auto_fixes", [])  # type: ignore[assignment]
    if fixes:
        click.secho("Auto-Fix Suggestions:", fg="blue")
        for fix in fixes[:4]:
            click.echo(f"  - {fix['title']} in {fix['path']}: {fix['snippet']}")


def _git_diff_or_empty() -> str:
    try:
        return subprocess.check_output(["git", "diff", "--cached"], text=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


if __name__ == "__main__":
    main()
