from click.testing import CliRunner

from diffguard.cli import main


def test_cli_init_creates_config():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["init"])

        assert result.exit_code == 0
        assert ".diffguard" in result.output


def test_cli_learn_and_stats(tmp_path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        from pathlib import Path

        Path("app.py").write_text("def hello():\n    return 'hi'\n", encoding="utf-8")
        result = runner.invoke(main, ["learn", "."])
        stats = runner.invoke(main, ["stats"])

        assert result.exit_code == 0
        assert "Learned 1 files" in result.output
        assert "files: 1" in stats.output


def test_cli_review_local_diff(tmp_path):
    diff = tmp_path / "change.diff"
    diff.write_text("diff --git a/a.py b/a.py\n+++ b/a.py\n@@\n+def changed():\n+    return 1\n", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(main, ["review", "--diff", str(diff), "--intent", "fix typo"])

    assert result.exit_code == 0
    assert "Verdict:" in result.output


def test_cli_review_v2_local_diff(tmp_path):
    diff = tmp_path / "change.diff"
    diff.write_text(
        "diff --git a/a.ts b/a.ts\n+++ b/a.ts\n@@\n+function changed(): string {\n+  return document.body.innerHTML;\n+}\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(main, ["review-v2", "--diff", str(diff), "--intent", "add changed helper"])

    assert result.exit_code == 0
    assert "Quality:" in result.output
    assert "Security Findings:" in result.output
