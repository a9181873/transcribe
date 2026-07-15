import io
import streamlit as st
import subprocess
import os
import sys
import zipfile
from pathlib import Path

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

DARK_CSS = """
<style>
/* ── 全域深色主題 ── */
[data-testid="stAppViewContainer"],
[data-testid="stApp"] {
    background: linear-gradient(160deg, #0f0f1a 0%, #1a1a2e 40%, #16213e 100%) !important;
    color: #e0e0e0 !important;
}

/* 頂部 Header */
[data-testid="stHeader"] {
    background: rgba(15, 15, 26, 0.85) !important;
    backdrop-filter: blur(12px) !important;
    border-bottom: 1px solid rgba(99, 102, 241, 0.15) !important;
}

/* 側邊欄 */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d0d1a 0%, #1a1a2e 100%) !important;
    border-right: 1px solid rgba(99, 102, 241, 0.12) !important;
}
[data-testid="stSidebar"] * {
    color: #c8c8d8 !important;
}

/* 所有文字 */
.stMarkdown, .stMarkdown p, .stMarkdown li, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3,
label, .stTextInput label, .stSelectbox label, .stCheckbox label {
    color: #e0e0e0 !important;
}

/* 標題漸層色 */
h1 {
    background: linear-gradient(135deg, #818cf8, #c084fc, #f472b6) !important;
    -webkit-background-clip: text !important;
    -webkit-text-fill-color: transparent !important;
    background-clip: text !important;
}

/* 輸入框 & 選單 */
.stTextInput > div > div,
.stSelectbox > div > div,
[data-baseweb="select"] > div {
    background-color: rgba(30, 30, 50, 0.8) !important;
    border: 1px solid rgba(99, 102, 241, 0.25) !important;
    color: #e0e0e0 !important;
    border-radius: 8px !important;
    transition: border-color 0.3s ease, box-shadow 0.3s ease !important;
}
.stTextInput > div > div:focus-within,
.stSelectbox > div > div:focus-within {
    border-color: rgba(129, 140, 248, 0.6) !important;
    box-shadow: 0 0 0 2px rgba(129, 140, 248, 0.15) !important;
}
input, textarea {
    color: #e0e0e0 !important;
}

/* 按鈕 */
.stButton > button {
    background: linear-gradient(135deg, #6366f1, #8b5cf6) !important;
    color: white !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    padding: 0.55rem 1.3rem !important;
    transition: all 0.3s ease !important;
    box-shadow: 0 4px 12px rgba(99, 102, 241, 0.25) !important;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #818cf8, #a78bfa) !important;
    box-shadow: 0 6px 20px rgba(99, 102, 241, 0.4) !important;
    transform: translateY(-1px) !important;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    background: rgba(20, 20, 35, 0.6) !important;
    border-radius: 10px !important;
    padding: 4px !important;
    gap: 4px !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: #9ca3af !important;
    border-radius: 8px !important;
    transition: all 0.3s ease !important;
}
.stTabs [aria-selected="true"] {
    background: rgba(99, 102, 241, 0.15) !important;
    color: #818cf8 !important;
}
.stTabs [data-baseweb="tab-highlight"] {
    background-color: #6366f1 !important;
}

/* 代碼區塊 */
.stCodeBlock, pre, code {
    background-color: rgba(10, 10, 20, 0.7) !important;
    border: 1px solid rgba(99, 102, 241, 0.12) !important;
    border-radius: 8px !important;
    color: #a5f3fc !important;
}

/* 成功/錯誤提示 */
.stAlert {
    border-radius: 10px !important;
    backdrop-filter: blur(8px) !important;
}

/* 檔案上傳區 */
[data-testid="stFileUploader"] {
    border: 2px dashed rgba(99, 102, 241, 0.3) !important;
    border-radius: 12px !important;
    background: rgba(20, 20, 35, 0.4) !important;
    transition: border-color 0.3s ease !important;
}
[data-testid="stFileUploader"]:hover {
    border-color: rgba(129, 140, 248, 0.5) !important;
}

/* Checkbox */
.stCheckbox label span {
    color: #c8c8d8 !important;
}

/* Divider */
hr {
    border-color: rgba(99, 102, 241, 0.15) !important;
}

/* Scrollbar */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: rgba(15, 15, 26, 0.5); }
::-webkit-scrollbar-thumb {
    background: rgba(99, 102, 241, 0.3);
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover { background: rgba(99, 102, 241, 0.5); }
</style>
"""

LIGHT_CSS = """
<style>
/* ── 亮色主題微調 ── */
h1 {
    background: linear-gradient(135deg, #4f46e5, #7c3aed, #db2777) !important;
    -webkit-background-clip: text !important;
    -webkit-text-fill-color: transparent !important;
    background-clip: text !important;
}
.stButton > button {
    background: linear-gradient(135deg, #6366f1, #8b5cf6) !important;
    color: white !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    padding: 0.55rem 1.3rem !important;
    transition: all 0.3s ease !important;
    box-shadow: 0 4px 12px rgba(99, 102, 241, 0.2) !important;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #818cf8, #a78bfa) !important;
    box-shadow: 0 6px 20px rgba(99, 102, 241, 0.35) !important;
    transform: translateY(-1px) !important;
}
</style>
"""

# 注入 CSS
if st.session_state.dark_mode:
    st.markdown(DARK_CSS, unsafe_allow_html=True)
else:
    st.markdown(LIGHT_CSS, unsafe_allow_html=True)

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

    # ── 語音辨識引擎 ──
    st.header("⚙️ 語音辨識 (ASR)")
    engine = st.selectbox(
        "核心引擎",
        ["funasr", "mlx_whisper"],
        index=0,
        format_func=lambda x: {
            "mlx_whisper": "⚡ MLX Whisper (Apple Silicon 加速)",
            "funasr": "🌏 FunASR (阿里巴巴中文語音)",
        }[x],
    )

    if engine == "mlx_whisper":
        model = "mlx-community/whisper-large-v3-turbo"
        st.info("⚡ 模型：`whisper-large-v3-turbo` — M4 極速首選")
    else:
        model = st.selectbox("FunASR 模型", ["iic/SenseVoiceSmall"], index=0)
        st.info("🎙️ 逐句輸出：VAD + 標點 + CAM++ 說話人辨識")

    quantize = "int8"
    if engine == "funasr":
        quantize = st.selectbox("量化 (Quantize)", ["none", "int8", "fp16"], index=1)

    st.divider()

    # ── 摘要引擎 ──
    st.header("🧠 摘要引擎")
    summary_engine = st.selectbox(
        "選擇摘要方式",
        ["gemini", "ollama"],
        index=0,
        format_func=lambda x: {
            "gemini": "☁️ Gemini (雲端 — Google AI)",
            "ollama": "🏠 Ollama (地端 — 完全離線)",
        }[x],
    )

    ollama_model = "qwen2.5:7b"
    ollama_url = "http://localhost:11434"
    if summary_engine == "ollama":
        ollama_model = st.selectbox(
            "地端模型",
            ["qwen2.5:7b", "qwen2.5:14b", "qwen2.5:3b", "llama3.1:8b"],
            index=0,
            format_func=lambda x: {
                "qwen2.5:7b": "⭐ Qwen 2.5 7B (中文首選、速度與品質均衡)",
                "qwen2.5:14b": "🔥 Qwen 2.5 14B (最佳品質、需較多記憶體)",
                "qwen2.5:3b": "⚡ Qwen 2.5 3B (超快速、輕量)",
                "llama3.1:8b": "🦙 Llama 3.1 8B (英文為主)",
            }[x],
        )
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
    if summary_engine == "ollama":
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
#### ☁️ Google Gemini 系列 (雲端)
| 項目 | 說明 |
| :--- | :--- |
| **模型 ID** | 由 CLI／環境變數設定（預設 `gemini-3.5-flash`） |
| **開發者** | Google DeepMind |
| **類型** | 雲端 API (需金鑰) |
| **授權** | Google API 服務條款 |
| **資料來源** | [Google AI Studio](https://aistudio.google.com/) ・ [官方文件](https://ai.google.dev/gemini-api/docs) |

**📝 模型介紹**

Google 最新一代的 Gemini 2.5 多模態大型語言模型。具備超強的長文理解能力（支援百萬 Token 上下文窗口），中英文摘要品質在雲端服務中名列前茅。Pro 版智慧最高，Flash 版速度最快。

**🎯 推薦場景**

| 場景 | 推薦程度 |
| :--- | :---: |
| 長篇會議摘要 | ⭐⭐⭐⭐⭐ |
| 多語混合內容 | ⭐⭐⭐⭐⭐ |
| 高精準度需求 | ⭐⭐⭐⭐⭐ |
| 離線/隱私需求 | ❌ 不適用 |
| 免費額度 | ⭐⭐⭐ (有限) |

> ☁️ **雲端首選！** 品質最高，但需要網路連線與 API 金鑰。有每日免費額度限制。
        """)

    with col4:
        st.markdown("""
#### 🏠 Qwen 2.5 系列 (地端 Ollama)
| 項目 | 說明 |
| :--- | :--- |
| **模型 ID** | `qwen2.5:7b` / `qwen2.5:14b` / `qwen2.5:3b` |
| **開發者** | 阿里雲通義千問團隊 |
| **參數量** | 3B / 7B / 14B 可選 |
| **類型** | 地端執行 (完全離線) |
| **授權** | Apache 2.0 |
| **資料來源** | [HuggingFace](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct) ・ [GitHub](https://github.com/QwenLM/Qwen2.5) ・ [Ollama](https://ollama.com/library/qwen2.5) |

**📝 模型介紹**

阿里雲通義千問團隊開發的第 2.5 代開源大型語言模型。在中文理解、摘要、邏輯推理等任務上表現卓越，是目前開源中文 LLM 的第一梯隊。透過 Ollama 在 Mac 本地執行，完全不依賴網路，資料隱私有保障。

**🎯 推薦場景**

| 場景 | 推薦程度 |
| :--- | :---: |
| 中文會議摘要 | ⭐⭐⭐⭐⭐ |
| 離線/隱私需求 | ⭐⭐⭐⭐⭐ |
| 免費使用 | ⭐⭐⭐⭐⭐ |
| 英文內容 | ⭐⭐⭐⭐ |
| 超長篇內容 (>10k字) | ⭐⭐⭐ |
| M4 Mac 執行速度 | ⭐⭐⭐⭐ |

> 🏠 **地端首選！** 完全免費、完全離線。7B 版在 M4 Mac 上速度飛快，品質逼近雲端模型。
        """)

    st.markdown("---")
    st.markdown("""
#### 🦙 Llama 3.1 8B (地端 Ollama)
| 項目 | 說明 |
| :--- | :--- |
| **模型 ID** | `llama3.1:8b` |
| **開發者** | Meta AI |
| **參數量** | ~8B |
| **類型** | 地端執行 (完全離線) |
| **授權** | Llama 3.1 Community License |
| **資料來源** | [HuggingFace](https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct) ・ [Ollama](https://ollama.com/library/llama3.1) |

**📝 模型介紹**

Meta AI 開發的開源大模型，在英文任務上表現強勁。支援 128K Token 上下文窗口，適合處理超長英文內容。中文能力也有一定水準，但不如 Qwen 2.5 系列。

**🎯 推薦場景**

| 場景 | 推薦程度 |
| :--- | :---: |
| 英文會議摘要 | ⭐⭐⭐⭐⭐ |
| 中文會議摘要 | ⭐⭐⭐ |
| 離線/隱私需求 | ⭐⭐⭐⭐⭐ |
| 超長篇英文內容 | ⭐⭐⭐⭐⭐ |
| M4 Mac 執行速度 | ⭐⭐⭐⭐ |

> 🦙 **英文場景備選。** 如果您的錄音以英文為主，Llama 3.1 是不錯的替代方案。
    """)

    # ── 總覽比較表 ──
    st.markdown("---")
    st.markdown("### 📊 模型總覽比較")
    st.markdown("""
| 模型 | 類型 | 中文 | 英文 | 速度 | 離線 | 推薦程度 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Whisper Large V3 Turbo (MLX)** | ASR | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ✅ | 🥇 唯一首選 |
| **FunASR SenseVoice** | ASR | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ✅ | 🥈 中文專精 |
| **Gemini 2.5 Pro/Flash** | LLM 摘要 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ❌ | 🥇 雲端首選 |
| **Qwen 2.5 7B** | LLM 摘要 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ✅ | 🥇 地端首選 |
| **Qwen 2.5 14B** | LLM 摘要 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ✅ | 🥈 地端高品質 |
| **Llama 3.1 8B** | LLM 摘要 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ✅ | 英文場景 |
    """)


st.markdown("---")
st.markdown(
    "💡 **提示：** 本介面會在背景執行 `transcribe_pro.py`，你可以在上方的終端區塊即時查看輸出進度。"
)
