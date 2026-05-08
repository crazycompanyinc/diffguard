"""FastAPI app for GitHub PR review webhooks and REST API."""

from __future__ import annotations

import os
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException, Request

from diffguard.core.db import DiffGuardDB
from diffguard.debater.debater import PRDebater
from diffguard.server.webhooks import should_review_pull_request, verify_signature


def create_app(db_path: str | Path = ".diffguard/diffguard.sqlite3") -> FastAPI:
    app = FastAPI(title="DiffGuard", version="0.1.0")
    db = DiffGuardDB(db_path)
    debater = PRDebater(db)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/stats")
    def stats() -> dict[str, int]:
        return db.stats()

    @app.post("/review")
    async def review(payload: dict[str, object]) -> dict[str, object]:
        diff = str(payload.get("diff", ""))
        intent = str(payload.get("intent", ""))
        if not diff or not intent:
            raise HTTPException(status_code=400, detail="diff and intent are required")
        return debater.review_diff(diff, intent).to_dict()

    @app.post("/webhook/github")
    async def github_webhook(request: Request, x_hub_signature_256: str | None = Header(default=None)) -> dict[str, object]:
        body = await request.body()
        if not verify_signature(body, x_hub_signature_256):
            raise HTTPException(status_code=401, detail="invalid signature")
        payload = await request.json()
        if not should_review_pull_request(payload):
            return {"status": "ignored"}
        review = await review_github_pr(payload, debater)
        return {"status": "reviewed", "review": review}

    return app


async def review_github_pr(payload: dict[str, object], debater: PRDebater) -> dict[str, object]:
    pr = payload["pull_request"]  # type: ignore[index]
    repo_info = payload["repository"]  # type: ignore[index]
    pr_number = int(pr["number"])
    repo = str(repo_info["full_name"])
    diff_url = str(pr["diff_url"])
    intent = f"{pr.get('title', '')}\n\n{pr.get('body') or ''}"
    token = os.getenv("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        diff_response = await client.get(diff_url, headers=headers)
        diff_response.raise_for_status()
        result = debater.review_diff(diff_response.text, intent, pr_number=pr_number, repo=repo)
        if token:
            comments_url = str(pr["comments_url"])
            await client.post(comments_url, headers=headers, json={"body": format_review_comment(result.to_dict())})
    return result.to_dict()


def format_review_comment(result: dict[str, object]) -> str:
    lines = [f"DiffGuard verdict: **{result['verdict']}** (confidence {result['confidence']})", ""]
    for argument in result.get("arguments", []):  # type: ignore[assignment]
        lines.append(f"- **{argument['severity']} {argument['type']}**: {argument['message']}")
    suggestions = result.get("suggestions", [])
    if suggestions:
        lines.append("")
        lines.append("Suggestions:")
        for suggestion in suggestions:  # type: ignore[assignment]
            lines.append(f"- {suggestion}")
    return "\n".join(lines)


app = create_app()
