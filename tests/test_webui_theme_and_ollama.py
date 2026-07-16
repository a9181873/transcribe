from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_classic_palette_replaces_gradient_theme():
    source = Path("webui.py").read_text(encoding="utf-8")

    assert "#F7F3EA" in source
    assert "#17324D" in source
    assert "#286F6B" in source
    assert "linear-gradient" not in source


def test_ollama_uses_one_fixed_local_model():
    app = AppTest.from_file("webui.py").run(timeout=20)
    app.selectbox[1].select("ollama").run(timeout=20)

    assert not list(app.exception)
    assert all(selectbox.label != "地端模型" for selectbox in app.selectbox)
    assert any("qwen2.5:7b" in caption.value for caption in app.caption)
