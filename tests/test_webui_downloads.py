import ast
from pathlib import Path


def test_every_streamlit_download_avoids_page_rerun():
    source = Path("webui.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    download_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "download_button"
    ]

    assert len(download_calls) == 3
    for call in download_calls:
        on_click = next(
            (keyword.value for keyword in call.keywords if keyword.arg == "on_click"),
            None,
        )
        assert isinstance(on_click, ast.Constant)
        assert on_click.value == "ignore"

    assert "直接下載逐字稿（備用）" in source


def test_deployment_includes_hourly_cleanup_service():
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "meeting-cleanup:" in compose
    assert "--retention-hours" in compose
    assert '"72"' in compose
    assert "--interval-seconds" in compose
    assert "disable: true" in compose
    assert '"3600"' in compose
    assert "job_retention.py" in dockerfile


def test_streamlit_minimum_supports_download_ignore_mode():
    for filename in ("requirements.txt", "requirements-oci.txt"):
        requirements = Path(filename).read_text(encoding="utf-8")
        assert "streamlit>=1.43,<2" in requirements
