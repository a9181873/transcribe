# AI 語音識別與結構化摘要工具

這是一款針對 Apple Silicon (M 系列晶片) 最佳化的語音辨識與自動摘要工具，支援本地端與雲端混合架構。

## 🌟 核心功能
* **語音辨識 (ASR)**：使用 `mlx-community/whisper-large-v3-turbo`，在 M 系列晶片上達到極速且高精準的中英文會議轉錄。
* **智慧摘要 (LLM)**：
  * **雲端模式**：整合 Google Gemini 2.5 系列 (Pro/Flash)，提供強大的長文脈絡理解。
  * **地端模式**：整合 Ollama (`Qwen 2.5 7B`)，實現完全離線、確保資料隱私的中文會議摘要。
* **友善介面**：提供 Streamlit WebUI，包含深色/亮色模式切換、批次處理能力以及詳盡的模型資訊頁面。

## 📝 更新日誌 (Update Log)

### [2026-04-05] 系統效能與架構優化
* **ASR 模型精簡**：移除了體積龐大且速度較慢的舊版 Whisper 模型 (large-v3, small, base)，全系統統一採用兼具速度與精準度的 `whisper-large-v3-turbo` (M4 最佳化)。
* **地端摘要引擎整合**：新增 Ollama 支援，使用者可於介面上選擇使用 `Qwen 2.5` 地端模型進行摘要，完全不依賴外部網路，保障機密會議隱私。
* **Gemini 引擎升級**：API 呼叫升級至 `gemini-2.5-pro`，並建立了自動降級容錯機制 (`2.5-flash` → `2.0-flash`)。
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

## 🔒 安全性聲明
本專案的 `config.ini`、Google Drive 憑證檔案 (`*.json`) 皆已加入 `.gitignore`，確保使用者的 API Key 與機密憑證絕對不會被上傳至雲端。
