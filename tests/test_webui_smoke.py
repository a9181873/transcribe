from streamlit.testing.v1 import AppTest


def test_webui_loads_and_exposes_model_selector():
    app = AppTest.from_file("webui.py").run(timeout=20)

    assert not list(app.exception)
    assert app.selectbox[0].label == "選擇模型"
