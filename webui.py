import io
import streamlit as st
import subprocess
import os
import sys
import zipfile
from pathlib import Path

from asr_catalog import (
    ASR_PROFILES,
    available_profile_keys,
    default_profile_key,
    detect_runtime_family,
    runtime_label,
)

st.set_page_config(page_title="AI 語音識別轉錄系統", page_icon="🎤", layout="wide")

# 公開部署預設只接受瀏覽器上傳，避免讓使用者任意讀寫伺服器檔案或探測內網。
# 本機開發若需要舊有的絕對路徑／批次功能，可設定 MEETING_ALLOW_LOCAL_PATHS=1。
ALLOW_LOCAL_PATHS = os.getenv("MEETING_ALLOW_LOCAL_PATHS", "0") == "1"
ALLOW_CUSTOM_OLLAMA = os.getenv("MEETING_ALLOW_CUSTOM_OLLAMA", "0") == "1"

# ═══════════════════════════════════════════════════════════════════════════════
# 🌙 深色模式 CSS 注入
# ═══════════════════════════════════════════════════════════════════════════════

if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False

CLASSIC_CSS = """
<style>
/* 經典編輯風格：海軍藍、暖白、低飽和青綠與少量金色 */
[data-testid="stAppViewContainer"],
[data-testid="stApp"] {
    background: var(--meeting-page) !important;
    color: var(--meeting-text) !important;
}

[data-testid="stHeader"] {
    background: color-mix(in srgb, var(--meeting-page) 94%, transparent) !important;
    border-bottom: 1px solid var(--meeting-border) !important;
    backdrop-filter: blur(10px) !important;
}

[data-testid="stSidebar"] {
    background: var(--meeting-sidebar) !important;
    border-right: 1px solid var(--meeting-border) !important;
}

.stMarkdown, .stMarkdown p, .stMarkdown li,
label, [data-testid="stCaptionContainer"] {
    color: var(--meeting-text) !important;
}

h1, h2, h3, h4 {
    color: var(--meeting-heading) !important;
    letter-spacing: -0.015em !important;
}

h1 {
    font-weight: 720 !important;
}

a {
    color: var(--meeting-accent) !important;
}

.stButton > button,
.stDownloadButton > button {
    background: var(--meeting-accent) !important;
    color: var(--meeting-on-accent) !important;
    border: 1px solid var(--meeting-accent) !important;
    border-radius: 7px !important;
    font-weight: 650 !important;
    box-shadow: 0 2px 8px var(--meeting-shadow) !important;
    transition: background-color 160ms ease, border-color 160ms ease !important;
}

.stButton > button:hover,
.stDownloadButton > button:hover {
    background: var(--meeting-accent-hover) !important;
    border-color: var(--meeting-accent-hover) !important;
}

.stTextInput input,
.stTextArea textarea,
.stNumberInput input,
[data-baseweb="select"] > div {
    background: var(--meeting-surface) !important;
    color: var(--meeting-text) !important;
    border-color: var(--meeting-border) !important;
    border-radius: 7px !important;
}

.stTextInput input:focus,
.stTextArea textarea:focus,
.stNumberInput input:focus,
[data-baseweb="select"] > div:focus-within {
    border-color: var(--meeting-accent) !important;
    box-shadow: 0 0 0 2px var(--meeting-focus) !important;
}

[data-baseweb="popover"],
[role="listbox"],
[role="option"] {
    background: var(--meeting-surface) !important;
    color: var(--meeting-text) !important;
}

[role="option"]:hover {
    background: var(--meeting-sidebar) !important;
}

.stTabs [data-baseweb="tab-list"] {
    gap: 1.25rem !important;
    border-bottom: 1px solid var(--meeting-border) !important;
}

.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: var(--meeting-muted) !important;
    border-radius: 0 !important;
}

.stTabs [aria-selected="true"] {
    color: var(--meeting-heading) !important;
}

.stTabs [data-baseweb="tab-highlight"] {
    background: var(--meeting-gold) !important;
}

[data-testid="stFileUploader"] {
    background: var(--meeting-surface) !important;
    border: 1.5px dashed var(--meeting-accent) !important;
    border-radius: 9px !important;
}

.stAlert {
    background: var(--meeting-surface) !important;
    color: var(--meeting-text) !important;
    border: 1px solid var(--meeting-border) !important;
    border-left: 4px solid var(--meeting-accent) !important;
    border-radius: 7px !important;
}

table {
    border-color: var(--meeting-border) !important;
}

thead tr {
    background: var(--meeting-sidebar) !important;
}

th, td {
    border-color: var(--meeting-border) !important;
}

pre, code, .stCodeBlock {
    background: var(--meeting-code) !important;
    color: var(--meeting-code-text) !important;
    border-color: var(--meeting-border) !important;
    border-radius: 6px !important;
}

hr {
    border-color: var(--meeting-border) !important;
}

[data-testid="stProgress"] > div > div > div > div {
    background: var(--meeting-accent) !important;
}

::-webkit-scrollbar { width: 7px; height: 7px; }
::-webkit-scrollbar-track { background: var(--meeting-page); }
::-webkit-scrollbar-thumb {
    background: var(--meeting-border-strong);
    border-radius: 8px;
}
</style>
"""

LIGHT_PALETTE_CSS = """
<style>
:root {
    --primary-color: #286F6B;
    --background-color: #F7F3EA;
    --secondary-background-color: #EEE7DA;
    --text-color: #1D2A33;
    --meeting-page: #F7F3EA;
    --meeting-surface: #FFFCF6;
    --meeting-sidebar: #EEE7DA;
    --meeting-text: #1D2A33;
    --meeting-muted: #5B6770;
    --meeting-heading: #17324D;
    --meeting-accent: #286F6B;
    --meeting-accent-hover: #1F5B58;
    --meeting-on-accent: #FFFFFF;
    --meeting-gold: #B78B3E;
    --meeting-border: #D8CDBB;
    --meeting-border-strong: #A99E8D;
    --meeting-code: #EDE7DC;
    --meeting-code-text: #17324D;
    --meeting-focus: rgba(40, 111, 107, 0.18);
    --meeting-shadow: rgba(23, 50, 77, 0.14);
}
</style>
"""

DARK_PALETTE_CSS = """
<style>
:root {
    --primary-color: #6CAAA5;
    --background-color: #111820;
    --secondary-background-color: #18232D;
    --text-color: #E9E4DA;
    --meeting-page: #111820;
    --meeting-surface: #18232D;
    --meeting-sidebar: #0D151C;
    --meeting-text: #E9E4DA;
    --meeting-muted: #AEB7BC;
    --meeting-heading: #D7E4EC;
    --meeting-accent: #6CAAA5;
    --meeting-accent-hover: #83BDB8;
    --meeting-on-accent: #0D1F21;
    --meeting-gold: #D2AE6D;
    --meeting-border: #344653;
    --meeting-border-strong: #657985;
    --meeting-code: #0D151C;
    --meeting-code-text: #B9D8D4;
    --meeting-focus: rgba(108, 170, 165, 0.22);
    --meeting-shadow: rgba(0, 0, 0, 0.28);
}
</style>
"""

# 注入色票與共用元件樣式
st.markdown(
    DARK_PALETTE_CSS if st.session_state.dark_mode else LIGHT_PALETTE_CSS,
    unsafe_allow_html=True,
)
st.markdown(CLASSIC_CSS, unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# 📐 主介面
# ═══════════════════════════════════════════════════════════════════════════════

st.title("🎤 會議錄音轉錄 & 結構化摘要工具")
st.markdown("透過此介面，你可以輕鬆勾選各項功能並執行 `transcribe_pro.py`。")

# ═══════════════════════════════════════════════════════════════════════════════
# 🎛️ 側邊欄
# ═══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    # ── 深色模式切換 ──
    st.header("🎨 介面主題")
    dark_toggle = st.toggle(
        "🌙 深色模式" if not st.session_state.dark_mode else "☀️ 亮色模式",
        value=st.session_state.dark_mode,
        help="切換深色/亮色介面主題",
    )
    if dark_toggle != st.session_state.dark_mode:
        st.session_state.dark_mode = dark_toggle
        st.rerun()

    st.divider()

    # ── 語音辨識模型 ──
    st.header("⚙️ 語音辨識模型")
    runtime_family = detect_runtime_family()
    profile_keys = available_profile_keys(runtime_family)
    selected_profile_key = st.selectbox(
        "選擇模型",
        profile_keys,
        index=profile_keys.index(default_profile_key(runtime_family)),
        format_func=lambda key: ASR_PROFILES[key].label,
        help="選項依執行程式的主機能力顯示；從 Mac 瀏覽 OCI 網站時仍使用 OCI 模型。",
    )
    selected_profile = ASR_PROFILES[selected_profile_key]
    engine = selected_profile.engine
    model = selected_profile.model
    quantize = selected_profile.quantize

    st.caption(f"執行環境：{runtime_label(runtime_family)}")
    st.info(
        f"**適用場景：** {selected_profile.scenario}\n\n"
        f"**適用硬體：** {selected_profile.hardware}\n\n"
        f"**記憶體：** {selected_profile.memory}\n\n"
        f"**辨識取向：** {selected_profile.accuracy}"
    )
    st.caption(selected_profile.note)

    st.divider()

    # ── 摘要引擎 ──
    st.header("🧠 摘要引擎")
    summary_engine = st.selectbox(
        "選擇摘要方式",
        ["gemini", "ollama"],
        index=0,
        format_func=lambda x: {
            "gemini": "☁️ Gemini 3.5 Flash（雲端・目前預設）",
            "ollama": "🏠 Ollama (地端 — 完全離線)",
        }[x],
    )

    gemini_model = "gemini-3.5-flash"
    ollama_model = "qwen2.5:7b"
    ollama_url = "http://localhost:11434"
    if summary_engine == "gemini":
        st.caption(f"實際摘要模型：`{gemini_model}`")
        st.info("適合正式會議紀錄、決議與待辦整理；逐字稿會送至 Google Gemini API。")
    else:
        st.caption("固定地端模型：`qwen2.5:7b`（中文摘要品質、速度與資源占用較均衡）")
        if ALLOW_CUSTOM_OLLAMA:
            ollama_url = st.text_input(
                "Ollama API 位址",
                value=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            )
        else:
            ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            st.caption(f"Ollama 位址：`{ollama_url}`（由伺服器環境變數設定）")
        st.info("💡 請確認 Ollama 已啟動 (`ollama serve`)")

    st.divider()

    # ── 摘要風格 ──
    st.header("📝 摘要風格")
    prompt_style = st.selectbox(
        "Prompt 風格",
        ["detailed", "concise", "action", "interview", "brainstorm", "classic"],
        index=0,
        format_func=lambda x: {
            "detailed": "📋 詳細結構化",
            "concise": "⚡ 精簡重點",
            "action": "🎯 行動導向",
            "interview": "🎤 訪談紀錄",
            "brainstorm": "💡 腦暴整理",
            "classic": "📝 經典簡易",
        }[x],
    )

    st.divider()

    # ── 雲端設定 ──
    st.header("☁️ 雲端設定")
    enable_gdrive = st.checkbox("啟用 Google Drive 下載/上傳", value=False)
    gdrive_id = ""
    if enable_gdrive:
        gdrive_id = st.text_input("Google Drive 檔案 ID (選填)")

# ═══════════════════════════════════════════════════════════════════════════════
# 📄 主內容區
# ═══════════════════════════════════════════════════════════════════════════════

tab1, tab2, tab3 = st.tabs(["🎵 單一檔案處理", "📁 資料夾批次處理", "📖 模型資訊"])


def build_common_args(output_dir):
    """組裝通用的命令列參數。"""
    args = ["--engine", engine]
    if engine == "funasr":
        args.extend(["--funasr-model", model, "--funasr-quantize", quantize])
    else:
        args.extend(["--model", model])
    args.extend(["--prompt-style", prompt_style])
    args.extend(["--summary-engine", summary_engine])
    if summary_engine == "gemini":
        args.extend(["--gemini-model", gemini_model])
    else:
        args.extend(["--ollama-model", ollama_model, "--ollama-url", ollama_url])
    args.extend(["--output", output_dir])
    if enable_gdrive:
        args.append("--enable-gdrive")
        if gdrive_id:
            args.extend(["--gdrive-id", gdrive_id])
    return args


def make_output_zip(result_dir):
    """將該次處理產生的所有檔案打包，方便手機一次下載。"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(Path(result_dir).rglob("*")):
            if path.is_file() and path.suffix != ".zip":
                archive.write(path, arcname=path.relative_to(result_dir))
    return buffer.getvalue()


def render_artifact_downloads(result_dir, stem, key_prefix):
    """呈現逐字稿、JSON、字幕、摘要與 ZIP 下載按鈕。"""
    artifact_specs = [
        (f"{stem}_會議摘要.txt", "⬇️ 下載會議摘要", "text/plain"),
        (f"{stem}_逐字稿.txt", "⬇️ 下載逐字稿", "text/plain"),
        (f"{stem}_逐句.json", "⬇️ 下載逐句 JSON", "application/json"),
        (f"{stem}_字幕.srt", "⬇️ 下載 SRT 字幕", "application/x-subrip"),
        (f"{stem}_字幕.vtt", "⬇️ 下載 VTT 字幕", "text/vtt"),
    ]
    columns = st.columns(3)
    for index, (filename, label, mime) in enumerate(artifact_specs):
        path = Path(result_dir) / filename
        if path.exists():
            with columns[index % len(columns)]:
                st.download_button(
                    label=label,
                    data=path.read_bytes(),
                    file_name=filename,
                    mime=mime,
                    key=f"{key_prefix}_{index}",
                    use_container_width=True,
                )
    zip_data = make_output_zip(result_dir)
    st.download_button(
        label="📦 一次下載全部檔案（ZIP）",
        data=zip_data,
        file_name=f"{stem}_會議記錄.zip",
        mime="application/zip",
        key=f"{key_prefix}_zip",
        use_container_width=True,
    )


def run_transcription(args, input_path=None, output_dir=None):
    """執行轉錄子程序，並在成功後於 UI 直接呈現摘要與逐字稿。"""
    import re

    with st.spinner("正在執行轉換… 這可能需要幾分鐘的時間，請稍候。"):
        process = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        )

        progress_bar = st.progress(0)
        status_text = st.empty()
        output_area = st.empty()
        full_output = ""
        current_progress = 0

        for line in iter(process.stdout.readline, ""):
            full_output += line

            # ── 解析進度 ──
            # 批次模式：處理第 X/Y 個檔案
            batch_match = re.search(r"處理第\s*(\d+)/(\d+)", line)
            if batch_match:
                done, total = int(batch_match.group(1)), int(batch_match.group(2))
                current_progress = done / total * 0.95
            # 單檔模式：依階段關鍵字推進
            elif "被支援" in line or "檔案格式" in line:
                current_progress = max(current_progress, 0.10)
            elif "正在執行語音轉錄" in line:
                current_progress = max(current_progress, 0.20)
            elif "逐字稿已儲存" in line:
                current_progress = max(current_progress, 0.60)
            elif "正在使用" in line and ("Gemini" in line or "Ollama" in line):
                current_progress = max(current_progress, 0.70)
            elif "摘要已儲存" in line:
                current_progress = max(current_progress, 0.90)
            elif "程式執行完成" in line:
                current_progress = 1.0

            progress_bar.progress(min(current_progress, 1.0))
            status_text.caption(f"⏳ 處理中... {int(current_progress * 100)}%")

            display_text = "".join(full_output.splitlines(True)[-50:])
            output_area.code(display_text, language="text")

        process.stdout.close()
        process.wait()

        # 清除進度 UI
        progress_bar.empty()
        status_text.empty()
        output_area.empty()

        if process.returncode == 0:
            st.success("✅ 處理完成！")
            st.balloons()

            # ── 嘗試讀取並顯示摘要與逐字稿 ──
            if input_path and output_dir:
                stem = Path(input_path).stem
                result_dir = Path(output_dir) / stem
                summary_file = result_dir / f"{stem}_會議摘要.txt"
                transcript_file = result_dir / f"{stem}_逐字稿.txt"

                # ── 📂 檔案儲存位置 ──
                st.info(f"📂 **檔案儲存位置：** `{result_dir.resolve()}`")

                # ── 📋 會議摘要（預設展開）──
                if summary_file.exists():
                    summary_text = summary_file.read_text(encoding="utf-8")
                    st.markdown("---")
                    st.markdown("### 📋 會議摘要")
                    st.markdown(summary_text)
                    word_count = len(summary_text)
                    st.caption(f"📊 摘要字數：{word_count:,} 字")

                    with st.expander("📋 複製摘要文字", expanded=False):
                        st.code(summary_text, language=None)

                # ── 📝 逐字稿（預設摺疊）──
                if transcript_file.exists():
                    transcript_text = transcript_file.read_text(encoding="utf-8")
                    with st.expander("📝 點此展開完整逐字稿", expanded=False):
                        st.text_area(
                            "逐字稿內容",
                            value=transcript_text,
                            height=400,
                            disabled=True,
                            label_visibility="collapsed",
                        )
                        t_count = len(transcript_text)
                        st.caption(f"📊 逐字稿字數：{t_count:,} 字")

                st.markdown("### ⬇️ 下載處理結果")
                render_artifact_downloads(result_dir, stem, "single_artifacts")
            elif output_dir:
                output_path = Path(output_dir)
                if output_path.exists() and any(output_path.rglob("*")):
                    st.markdown("### ⬇️ 下載批次處理結果")
                    render_artifact_downloads(output_path, "batch", "batch_artifacts")
        else:
            st.error(f"❌ 處理失敗，返回碼：{process.returncode}")


with tab1:
    st.subheader("🎵 單一檔案處理")
    uploaded_file = st.file_uploader(
        "👉 點擊並選擇音訊檔案", type=["wav", "mp3", "m4a", "mp4", "flac", "ogg", "aac"]
    )
    input_file = ""
    output_dir_1 = "./output"
    if ALLOW_LOCAL_PATHS:
        input_file = st.text_input(
            "或者手動輸入音訊檔案的絕對路徑 (例如：/Users/jy/Downloads/test.m4a)"
        )
        output_dir_1 = st.text_input("輸出目錄", value="./output", key="out1")
    else:
        st.caption("公開上傳模式：檔案會儲存於伺服器的隔離輸出目錄，完成後可直接下載。")

    if st.button("🚀 開始轉錄 (單一檔案)", key="btn_single"):
        final_input_path = ""
        if uploaded_file is not None:
            os.makedirs(output_dir_1, exist_ok=True)
            safe_name = Path(uploaded_file.name).name
            final_input_path = os.path.join(output_dir_1, safe_name)
            with open(final_input_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
        elif input_file:
            final_input_path = input_file

        if not final_input_path and not gdrive_id:
            st.error("請上傳檔案、提供音訊檔案路徑，或啟用 Google Drive 並填寫 ID。")
        else:
            args = [sys.executable, "transcribe_pro.py", "--mode", "single"]
            if final_input_path:
                args.extend(["--file", final_input_path])
            args.extend(build_common_args(output_dir_1))
            run_transcription(
                args, input_path=final_input_path, output_dir=output_dir_1
            )

with tab2:
    if not ALLOW_LOCAL_PATHS:
        st.info("公開部署目前提供手機單檔上傳；伺服器資料夾批次功能已停用。")
    else:
        st.subheader("📁 資料夾批次處理")
        input_folder = st.text_input(
            "請輸入資料夾的絕對路徑 (例如：/Users/jy/Downloads)"
        )
        output_dir_2 = st.text_input("輸出目錄", value="./output", key="out2")

        if st.button("🚀 開始批次轉錄 (資料夾)", key="btn_batch"):
            if not input_folder:
                st.error("請提供資料夾路徑。")
            else:
                args = [
                    sys.executable,
                    "transcribe_pro.py",
                    "--mode",
                    "batch",
                    "--folder",
                    input_folder,
                ]
                args.extend(build_common_args(output_dir_2))
                run_transcription(args, output_dir=output_dir_2)

# ═══════════════════════════════════════════════════════════════════════════════
# 📖 模型資訊分頁
# ═══════════════════════════════════════════════════════════════════════════════

with tab3:
    st.subheader("📖 系統使用的 AI 模型一覽")
    st.markdown(
        "以下列出本系統所有語音辨識 (ASR) 與文字摘要 (LLM) 模型的詳細資訊、推薦場景與評級。"
    )

    # ── 語音辨識模型 ──
    st.markdown("---")
    st.markdown("### 🎙️ 語音辨識 (ASR) 模型")

    st.markdown("""
#### ⭐ MLX Whisper Large V3 Turbo
| 項目 | 說明 |
| :--- | :--- |
| **模型 ID** | `mlx-community/whisper-large-v3-turbo` |
| **開發者** | OpenAI（原始模型）→ MLX Community（Apple Silicon 優化版） |
| **參數量** | ~809M（經蒸餾壓縮，Decoder 僅 4 層） |
| **架構** | Whisper (Encoder-Decoder Transformer) |
| **授權** | MIT License |
| **RAM 佔用** | 約 1.6 GB — 極為輕量 |
| **資料來源** | [HuggingFace 模型頁](https://huggingface.co/mlx-community/whisper-large-v3-turbo) |

**📝 模型介紹**

由 OpenAI 在 2024 年底推出的 Whisper Large V3 Turbo，是透過知識蒸餾 (Knowledge Distillation) 從 Large V3 壓縮而來。MLX Community 將其轉換為 Apple MLX 格式，使其能充分利用 M 系列晶片的 Neural Engine 與統一記憶體，達到接近即時的轉錄速度。相比完整版 Large V3（1550M 參數、佔 3GB+ RAM），Turbo 版在中文會議場景下精準度幾乎無差異，但**速度快了數倍、RAM 省了一半**。

**🎯 推薦場景**

| 場景 | 推薦程度 |
| :--- | :---: |
| 多人中文會議錄音 | ⭐⭐⭐⭐⭐ |
| 英文會議錄音 | ⭐⭐⭐⭐⭐ |
| 多語混用 (中英夾雜) | ⭐⭐⭐⭐ |
| 即時/快速轉錄 | ⭐⭐⭐⭐⭐ |
| 嘈雜環境 | ⭐⭐⭐⭐ |
| 長時間錄音 (>1hr) | ⭐⭐⭐⭐⭐ |

> 💡 **本系統唯一保留的 Whisper 模型！** 在 M4 Mac 上速度最快、RAM 最省，中文會議精準度極高。
    """)

    st.markdown("---")

    st.markdown("""
#### 🌏 FunASR SenseVoice Small
| 項目 | 說明 |
| :--- | :--- |
| **模型 ID** | `iic/SenseVoiceSmall` |
| **開發者** | 阿里巴巴達摩院 (DAMO Academy) |
| **參數量** | 以官方模型卡為準（Small 版本） |
| **架構** | SenseVoice (基於 Paraformer 改進) |
| **授權** | Apache 2.0 |
| **資料來源** | [ModelScope 模型頁](https://modelscope.cn/models/iic/SenseVoiceSmall) ・ [GitHub](https://github.com/FunAudioLLM/SenseVoice) |

**📝 模型介紹**

阿里巴巴達摩院開發的多語言語音理解模型。除了語音轉文字，還具備情感識別、音訊事件偵測等功能；本系統另接入 VAD、標點與 CAM++，輸出逐句時間戳及說話人標籤。

**🎯 推薦場景**

| 場景 | 推薦程度 |
| :--- | :---: |
| 中文會議錄音 | ⭐⭐⭐⭐⭐ |
| 粵語/方言 | ⭐⭐⭐⭐ |
| 英文會議錄音 | ⭐⭐⭐ |
| 情感分析 | ⭐⭐⭐⭐ |
| 即時/快速轉錄 | ⭐⭐⭐⭐ |
| 嘈雜環境 | ⭐⭐⭐⭐ |

> 🌏 **中文語音專家！** 如果您的錄音以中文為主且需要情感標記，這是極佳選擇。
    """)

    # ── 摘要 LLM 模型 ──
    st.markdown("---")
    st.markdown("### 🧠 文字摘要 (LLM) 模型")

    col3, col4 = st.columns(2)

    with col3:
        st.markdown("""
#### ☁️ Gemini 3.5 Flash（雲端）
| 項目 | 說明 |
| :--- | :--- |
| **模型 ID** | `gemini-3.5-flash` |
| **開發者** | Google DeepMind |
| **類型** | 雲端 API (需金鑰) |
| **授權** | Google API 服務條款 |
| **資料來源** | [Google AI Studio](https://aistudio.google.com/) ・ [官方文件](https://ai.google.dev/gemini-api/docs) |

**📝 模型介紹**

目前介面使用 Gemini 3.5 Flash，適合將長篇逐字稿整理成結論、決議、待辦、風險與未決問題。

**🎯 推薦場景**

| 場景 | 推薦程度 |
| :--- | :---: |
| 長篇會議摘要 | ⭐⭐⭐⭐⭐ |
| 多語混合內容 | ⭐⭐⭐⭐⭐ |
| 高精準度需求 | ⭐⭐⭐⭐⭐ |
| 離線/隱私需求 | ❌ 不適用 |
| 免費額度 | ⭐⭐⭐ (有限) |

> ☁️ **雲端預設。** 需要網路連線與 API 金鑰；逐字稿會送至 Google Gemini API。
        """)

    with col4:
        st.markdown("""
#### 🏠 Qwen 2.5 7B（地端 Ollama）
| 項目 | 說明 |
| :--- | :--- |
| **固定模型 ID** | `qwen2.5:7b` |
| **選擇理由** | 中文摘要、速度與資源占用均衡 |
| **類型** | 地端執行（完全離線） |
| **模型安裝** | 只需 `ollama pull qwen2.5:7b` |
| **資料來源** | [HuggingFace](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct) ・ [Ollama](https://ollama.com/library/qwen2.5) |

**🎯 適用場景**

| 場景 | 推薦程度 |
| :--- | :---: |
| 中文會議摘要 | ⭐⭐⭐⭐⭐ |
| 離線／隱私需求 | ⭐⭐⭐⭐⭐ |
| Mac M4 24GB 日常使用 | ⭐⭐⭐⭐ |
| 中英文混合內容 | ⭐⭐⭐⭐ |

> 介面不再列出其他 Ollama 模型，避免誤裝多個模型占用磁碟；只保留 `qwen2.5:7b`。
        """)

    # ── 總覽比較表 ──
    st.markdown("---")
    st.markdown("### 📊 模型總覽比較")
    st.markdown("""
| 模型 | 類型 | 中文 | 英文 | 速度 | 離線 | 推薦程度 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Whisper Large V3 Turbo (MLX)** | ASR | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ✅ | 🥇 唯一首選 |
| **FunASR SenseVoice** | ASR | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ✅ | 🥈 中文專精 |
| **Gemini 3.5 Flash** | LLM 摘要 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ❌ | 🥇 雲端首選 |
| **Qwen 2.5 7B** | LLM 摘要 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ✅ | 🥇 唯一地端選項 |
    """)


st.markdown("---")
st.markdown(
    "💡 **提示：** 本介面會在背景執行 `transcribe_pro.py`，你可以在上方的終端區塊即時查看輸出進度。"
)
