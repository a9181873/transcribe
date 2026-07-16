# AI 語音識別與結構化摘要工具

這是一款以手機錄音上傳為主要場景的語音辨識與會議紀錄工具，支援 Apple Silicon 本機與 OCI Linux 部署。

## 🌟 核心功能
* **語音辨識 (ASR)**：預設使用 `iic/SenseVoiceSmall`，搭配 VAD、標點與 CAM++ 說話人辨識，輸出逐句時間戳。
  * Apple Silicon 亦可選擇 `mlx-community/whisper-large-v3-turbo`。
* **智慧摘要 (LLM)**：
  * **雲端模式**：使用 Google GenAI SDK 與可設定的 Gemini 模型。
  * **地端模式**：整合 Ollama (`Qwen 2.5 7B`)，實現完全離線、確保資料隱私的中文會議摘要。
* **友善介面**：提供 Streamlit WebUI，包含深色/亮色模式切換、批次處理能力以及詳盡的模型資訊頁面。
* **可下載輸出**：每次處理產生摘要、逐字稿、逐句 JSON、SRT、VTT，並可一次下載 ZIP。

## 📝 更新日誌 (Update Log)

### [2026-07-16] 手機會議紀錄輸出
* 新增 SenseVoiceSmall 的 VAD、標點與 CAM++ 說話人辨識流程。
* 新增逐句 JSON、SRT、VTT 與 ZIP 下載。
* 新增 OCI Linux CPU Dockerfile、Compose 與 Caddy 反向代理片段。

### [2026-04-05] 系統效能與架構優化
* **ASR 模型精簡**：移除了體積龐大且速度較慢的舊版 Whisper 模型 (large-v3, small, base)，全系統統一採用兼具速度與精準度的 `whisper-large-v3-turbo` (M4 最佳化)。
* **地端摘要引擎整合**：新增 Ollama 支援，使用者可於介面上選擇使用 `Qwen 2.5` 地端模型進行摘要，完全不依賴外部網路，保障機密會議隱私。
* **Gemini 引擎升級**：改用 `google-genai` SDK，模型 ID 可透過 CLI 設定，預設使用 `gemini-3.5-flash`。
* **介面 UI 升級**：
  * 新增全域「🌙 深色模式」開關。
  * 新增「📖 模型資訊」分頁，詳細列出每個模型的參數量、來源、適用場景與效能星級評分。
* **磁碟快取清理**：清除了舊版 ModelScope 與 HuggingFace 的閒置快取，釋放約 1.7GB 空間。

## 🚀 快速啟動
```bash
# 安裝依賴
pip install -r requirements.txt

# 啟動 Web 介面
./啟動Web介面.command
```

## ASR 模型選擇與適用場景

Web UI 會依「執行程式的主機」顯示真正可用的模型，而不是依瀏覽器裝置判斷。從 Mac 瀏覽 OCI 網站時，運算仍發生在 OCI。

| 模型 | 適用環境 | 適用場景 | 資源取向 |
| --- | --- | --- | --- |
| SenseVoiceSmall | OCI ARM／一般 CPU | 中文長會議、多人說話、批次處理 | 省資源、支援 VAD／標點／CAM++ |
| Whisper Large V3 Turbo | Apple Silicon，16GB+ | 中英混講、一般會議 | Mac M4 24GB 日常推薦 |
| Whisper Large V3 4-bit | Apple Silicon，16GB+ | 希望降低記憶體並試用 Large V3 | 省記憶體實驗選項 |
| Whisper Large V3 FP16 | Apple Silicon，24GB+ | 重要錄音、精度優先 | 高占用，建議先關閉大型應用程式 |

Mac M4 24GB 預設使用 Turbo，以保留瀏覽器、通訊與辦公軟體的日常記憶體空間。Qwen3-ASR 尚未列入 Mac 選單，因官方執行路徑目前以 CUDA／vLLM 為主。

## 摘要模型與會議紀錄規則

預設摘要模型為 **Gemini 3.5 Flash**（模型 ID：`gemini-3.5-flash`）。UI 會明確顯示實際模型及資料會送往雲端 API。Ollama 僅在使用者自行提供可連線的地端服務時使用，介面固定採用 `qwen2.5:7b`，避免誤裝多個模型占用磁碟。

所有摘要風格都套用共同事實約束：繁體中文、不得虛構、不得自行推定負責人或期限，並區分已決議、提案、討論中與未決問題。正式會議紀錄固定包含一頁摘要、決議、待辦、風險、未決問題及下次追蹤。

## OCI 部署

OCI 使用 CPU 版本的 `Dockerfile` 與 `docker-compose.yml`；MLX 不會安裝在 Linux 映像中。

```bash
cp .env.example .env  # 填入 GEMINI_API_KEY
docker compose up -d --build
```

將 `deploy/Caddyfile.meeting.snippet` 加入 OCI Caddyfile，並將 `meeting.dky.tw` 指向 OCI 伺服器，即可透過 HTTPS 使用。公開部署預設只允許瀏覽器上傳，完成後可直接下載 TXT、JSON、SRT、VTT 或 ZIP；如需本機資料夾批次功能，請在環境變數設定 `MEETING_ALLOW_LOCAL_PATHS=1`。

## 🔒 安全性聲明
本專案的 `config.ini`、Google Drive 憑證檔案 (`*.json`) 皆已加入 `.gitignore`，確保使用者的 API Key 與機密憑證絕對不會被上傳至雲端。
