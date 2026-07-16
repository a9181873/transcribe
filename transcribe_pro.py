#!/usr/bin/env python3
"""
transcribe_pro.py — 會議錄音轉錄 & 結構化摘要工具 (優化整合版)

整合自所有歷史版本的精華：
  - 原版：完整 Google Drive 上傳/下載、手動音訊預處理
  - V1.1：音訊格式驗證、FFmpeg 多層 fallback、Jupyter 相容
  - V2+：多引擎架構（MlxWhisper / FunASR）
  - V3.1：DSPy 結構化專家版 Prompt、最新 Gemini 模型

用法：
  python transcribe_pro.py                            # 使用預設設定
  python transcribe_pro.py --mode batch --folder /path
  python transcribe_pro.py --mode single --file a.m4a
  python transcribe_pro.py --mode interactive
  python transcribe_pro.py --prompt-style concise
  python transcribe_pro.py --list-prompts
  python transcribe_pro.py --enable-gdrive             # 啟用 Google Drive 功能
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import tempfile
import time
from configparser import ConfigParser
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator, List, Optional, Tuple

from summary_prompt_rules import apply_summary_rules

import torch
import torchaudio

# ─── 日誌設定 ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",  # 保持簡潔的 emoji 風格輸出
)
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 🔧 延遲載入（Lazy Import）— 避免未安裝的套件阻塞啟動
# ═══════════════════════════════════════════════════════════════════════════════


def _try_import_mlx_whisper():
    """嘗試載入 mlx-whisper 套件。"""
    try:
        import mlx_whisper

        return mlx_whisper
    except ImportError:
        return None


def _try_import_funasr():
    """嘗試載入 FunASR 套件。"""
    try:
        from funasr import AutoModel

        return AutoModel
    except ImportError:
        return None


def _try_import_google_drive():
    """嘗試載入 Google Drive 相關套件。"""
    try:
        import io as _io
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build, Resource
        from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
        from googleapiclient.errors import HttpError

        return {
            "io": _io,
            "Credentials": Credentials,
            "InstalledAppFlow": InstalledAppFlow,
            "Request": Request,
            "build": build,
            "Resource": Resource,
            "MediaIoBaseDownload": MediaIoBaseDownload,
            "MediaFileUpload": MediaFileUpload,
            "HttpError": HttpError,
        }
    except ImportError:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# ⚙️  設定管理
# ═══════════════════════════════════════════════════════════════════════════════

# 支援的音訊副檔名（來自 V1.1 的格式驗證）
SUPPORTED_EXTENSIONS: set[str] = {
    ".wav",
    ".mp3",
    ".m4a",
    ".mp4",
    ".flac",
    ".ogg",
    ".aac",
}

# Google Drive API 權限範圍（來自原版）
SCOPES = ["https://www.googleapis.com/auth/drive"]


@dataclass
class AppConfig:
    """集中管理所有應用程式設定。"""

    # ASR 引擎：mlx_whisper | funasr
    # FunASR 是目前唯一能在本流程直接產生逐句說話人資訊的引擎。
    asr_engine: str = "funasr"

    # Whisper 模型（mlx_whisper 生效）
    # ┌─────────────────────────────────────────────────────────────────────┐
    # │  M4 24GB RAM 唯一推薦（MLX 專用）：                                 │
    # │  mlx-community/whisper-large-v3-turbo  ⭐ 速度快、精準、低 RAM       │
    # └─────────────────────────────────────────────────────────────────────┘
    whisper_model: str = (
        "mlx-community/whisper-large-v3-turbo"  # ⭐ M4 唯一預設 (MLX專用)
    )

    # FunASR 模型
    funasr_model: str = "iic/SenseVoiceSmall"

    # FunASR 量化設定：none | int8 | fp16（來自 V2）
    funasr_quantize: str = "int8"

    # 處理模式：single | batch | interactive
    mode: str = "batch"

    # 路徑
    single_file: str = ""
    batch_folder: str = "/Users/jy/Downloads"
    output_dir: Path = field(default_factory=lambda: Path("./output"))

    # 摘要 Prompt 風格
    prompt_style: str = "detailed"

    # 摘要引擎：gemini | ollama
    summary_engine: str = "gemini"
    gemini_model: str = "gemini-3.5-flash"

    # Ollama 地端模型設定
    ollama_model: str = "qwen2.5:7b"  # ⭐ 地端中文摘要首選
    ollama_base_url: str = "http://localhost:11434"  # Ollama 預設 API 位址

    # Google Drive 設定（來自原版 & V1.1）
    enable_gdrive: bool = False
    gdrive_file_id: str = ""
    gdrive_upload_folder_id: str = ""

    # Gemini API Key
    gemini_api_key: str = ""

    def __post_init__(self) -> None:
        self.output_dir = Path(self.output_dir)

    def load_api_key_from_config(self) -> None:
        """從 config.ini 或環境變數載入 Gemini API Key。"""
        if self.gemini_api_key:
            return
        config = ConfigParser()
        config_path = Path(__file__).parent / "config.ini"
        try:
            if config_path.exists():
                config.read(config_path, encoding="utf-8")
                self.gemini_api_key = config.get(
                    "DEFAULT", "GEMINI_API_KEY", fallback=""
                )
        except Exception:
            pass
        if not self.gemini_api_key:
            self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")


# ═══════════════════════════════════════════════════════════════════════════════
# ⏱️  通用工具
# ═══════════════════════════════════════════════════════════════════════════════


def format_duration(seconds: float) -> str:
    """將秒數格式化為「X 分 Y 秒」。"""
    minutes, sec = divmod(int(seconds), 60)
    return f"{minutes} 分 {sec} 秒"


@contextmanager
def timer(label: str) -> Generator[None, None, None]:
    """計時用 context manager，結束後自動印出耗時。"""
    start = time.time()
    yield
    elapsed = time.time() - start
    log.info("✅ %s 耗時: %s", label, format_duration(elapsed))


def detect_device() -> str:
    """偵測最佳可用計算裝置（來自原版與 V2+ 的合併邏輯）。"""
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def validate_audio_format(file_path: str) -> bool:
    """驗證音訊檔案格式是否被支援（來自 V1.1）。"""
    ext = Path(file_path).suffix.lower()
    if ext in SUPPORTED_EXTENSIONS:
        log.info("✅ 檔案格式 %s 被支援。", ext)
        return True
    log.warning(
        "⚠️ 檔案格式 %s 可能不被支援。支援格式: %s",
        ext,
        ", ".join(sorted(SUPPORTED_EXTENSIONS)),
    )
    return False


def _clean_asr_text(text: str) -> str:
    """清理 SenseVoice 的語言／情緒／事件控制標籤。"""
    cleaned = text.strip()
    try:
        from funasr.utils.postprocess_utils import rich_transcription_postprocess

        cleaned = rich_transcription_postprocess(cleaned)
    except (ImportError, TypeError, AttributeError):
        # 沒有 FunASR 時仍可處理 MLX／測試資料。
        cleaned = re.sub(r"<\|[^>]+\|>", "", cleaned)
    return cleaned.strip()


def _speaker_key(value: object) -> Optional[str]:
    """將不同引擎的說話人欄位統一成穩定字串。"""
    if value is None or value == "":
        return None
    value_text = str(value)
    return value_text if value_text.startswith("speaker_") else f"speaker_{value_text}"


def _speaker_label(value: Optional[str]) -> str:
    """將 speaker_0 轉成適合人閱讀的「說話人 A」。"""
    if not value:
        return "說話人未知"
    suffix = value.removeprefix("speaker_")
    if suffix.isdigit():
        number = int(suffix)
        if number < 26:
            return f"說話人 {chr(ord('A') + number)}"
    return value


def _format_timestamp(seconds: Optional[float], separator: str = ",") -> str:
    """格式化字幕時間；未知時間以 00:00:00.000 表示。"""
    total_ms = max(0, int(round((seconds or 0.0) * 1000)))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"


def _normalise_chunks(chunks: list[dict]) -> list[dict]:
    """統一各 ASR 引擎的逐句結果格式。"""
    normalised: list[dict] = []
    for chunk in chunks:
        start, end = chunk.get("timestamp", (None, None))
        text = _clean_asr_text(str(chunk.get("text", "")))
        if not text:
            continue
        normalised.append(
            {
                "start": float(start) if start is not None else None,
                "end": float(end) if end is not None else None,
                "speaker": _speaker_key(chunk.get("speaker")),
                "text": text,
            }
        )
    return normalised


def write_transcription_artifacts(
    output_dir: Path,
    stem: str,
    transcribed_text: str,
    chunks: list[dict],
) -> dict[str, Path]:
    """輸出可閱讀逐字稿及可供其他系統使用的字幕／JSON 檔案。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    segments = _normalise_chunks(chunks)
    if not segments and transcribed_text.strip():
        segments = [
            {
                "start": None,
                "end": None,
                "speaker": None,
                "text": _clean_asr_text(transcribed_text),
            }
        ]

    transcript_lines = []
    for segment in segments:
        if segment["start"] is None:
            time_text = "未知時間"
        else:
            time_text = f"{_format_timestamp(segment['start'], '.')}–{_format_timestamp(segment['end'], '.')}"
        transcript_lines.append(
            f"[{time_text}] {_speaker_label(segment['speaker'])}：{segment['text']}"
        )
    transcript_text = (
        "\n\n".join(transcript_lines) if transcript_lines else transcribed_text.strip()
    )

    json_path = output_dir / f"{stem}_逐句.json"
    json_path.write_text(
        json.dumps({"version": 1, "segments": segments}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    srt_blocks = []
    vtt_blocks = []
    for index, segment in enumerate(segments, start=1):
        if segment["start"] is None:
            continue
        speaker_text = f"{_speaker_label(segment['speaker'])}："
        srt_blocks.append(
            f"{index}\n{_format_timestamp(segment['start'])} --> {_format_timestamp(segment['end'])}\n{speaker_text}{segment['text']}"
        )
        vtt_blocks.append(
            f"{_format_timestamp(segment['start'], '.')} --> {_format_timestamp(segment['end'], '.')}\n{speaker_text}{segment['text']}"
        )

    srt_path = output_dir / f"{stem}_字幕.srt"
    srt_path.write_text(
        "\n\n".join(srt_blocks) + ("\n" if srt_blocks else ""), encoding="utf-8"
    )
    vtt_path = output_dir / f"{stem}_字幕.vtt"
    vtt_path.write_text(
        "WEBVTT\n\n" + "\n\n".join(vtt_blocks) + ("\n" if vtt_blocks else ""),
        encoding="utf-8",
    )

    transcript_path = output_dir / f"{stem}_逐字稿.txt"
    transcript_path.write_text(transcript_text, encoding="utf-8")
    return {
        "transcript": transcript_path,
        "json": json_path,
        "srt": srt_path,
        "vtt": vtt_path,
    }


def setup_torchaudio_backend() -> None:
    """設定 torchaudio 音訊後端，含 fallback（來自 V1.1）。"""
    if hasattr(torchaudio, "set_audio_backend"):
        try:
            torchaudio.set_audio_backend("ffmpeg")
            log.info("✅ Torchaudio backend: FFmpeg")
            log.info("📁 支援格式：WAV, MP3, M4A, MP4, FLAC, OGG, AAC")
        except RuntimeError:
            try:
                torchaudio.set_audio_backend("soundfile")
                log.info("✅ Fallback backend: soundfile")
            except RuntimeError:
                log.warning("⚠️ 使用預設 backend，部分格式可能不支援。")
    else:
        log.info(
            "✅ Torchaudio (>= 2.1) backend auto setup. FFmpeg support is automatically used if available."
        )


# ═══════════════════════════════════════════════════════════════════════════════
# ☁️  Google Drive 功能模組（來自原版 & V1.1）
# ═══════════════════════════════════════════════════════════════════════════════


class GoogleDriveManager:
    """封裝 Google Drive 的認證、下載、上傳功能。"""

    def __init__(self) -> None:
        self._gd = _try_import_google_drive()
        if self._gd is None:
            raise ImportError(
                "Google Drive 相關套件未安裝。請執行：\n"
                "pip install google-auth google-auth-oauthlib google-api-python-client"
            )
        self.service = None

    def authenticate(self) -> bool:
        """驗證 Google Drive API 並建立服務物件。"""
        gd = self._gd
        creds = None
        try:
            script_dir = (
                Path(__file__).parent if "__file__" in globals() else Path.cwd()
            )
            token_path = script_dir / "token.json"
            credentials_path = script_dir / "credentials.json"

            if token_path.exists():
                creds = gd["Credentials"].from_authorized_user_file(
                    str(token_path), SCOPES
                )

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(gd["Request"]())
                else:
                    if not credentials_path.exists():
                        log.error("❌ 找不到 'credentials.json': %s", credentials_path)
                        return False
                    flow = gd["InstalledAppFlow"].from_client_secrets_file(
                        str(credentials_path), SCOPES
                    )
                    creds = flow.run_local_server(port=0)
                token_path.write_text(creds.to_json(), encoding="utf-8")

            self.service = gd["build"]("drive", "v3", credentials=creds)
            log.info("✅ Google Drive 驗證成功。")
            return True
        except Exception as e:
            log.error("❌ Google Drive 驗證失敗: %s", e)
            return False

    def download(self, file_id: str, destination: str) -> Optional[str]:
        """從 Google Drive 下載檔案。"""
        if not self.service:
            log.error("❌ 尚未完成 Google Drive 驗證。")
            return None
        gd = self._gd
        try:
            request = self.service.files().get_media(fileId=file_id)
            fh = gd["io"].FileIO(destination, "wb")
            downloader = gd["MediaIoBaseDownload"](fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                print(f"\r📥 下載進度 {int(status.progress() * 100)}%", end="")
            print("\n✅ 檔案下載成功。")
            return destination
        except Exception as e:
            log.error("❌ 下載失敗: %s", e)
            return None

    def upload(
        self, file_path: str, parent_folder_id: Optional[str] = None
    ) -> Optional[str]:
        """上傳檔案至 Google Drive。"""
        if not self.service:
            log.error("❌ 尚未完成 Google Drive 驗證。")
            return None
        gd = self._gd
        try:
            file_metadata: dict = {"name": Path(file_path).name}
            if parent_folder_id:
                file_metadata["parents"] = [parent_folder_id]
            media = gd["MediaFileUpload"](file_path, resumable=True)
            file = (
                self.service.files()
                .create(body=file_metadata, media_body=media, fields="id")
                .execute()
            )
            fid = file.get("id")
            log.info("✅ '%s' 已上傳，ID: %s", Path(file_path).name, fid)
            return fid
        except Exception as e:
            log.error("❌ 上傳失敗: %s", e)
            return None


# ═══════════════════════════════════════════════════════════════════════════════
# 🎙️  ASR 處理器（策略模式 + 各版本最佳實踐整合）
# ═══════════════════════════════════════════════════════════════════════════════


class BaseAudioProcessor:
    """所有 ASR 處理器的基底類別。"""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.device = detect_device()
        log.info("🚀 初始化 %s...", self.__class__.__name__)
        log.info("💻 使用硬體: %s", self.device.upper())

    def transcribe_audio(self, audio_path: str) -> Tuple[str, list]:
        """轉錄音訊。子類別必須覆寫此方法。"""
        raise NotImplementedError("子類別必須實作 `transcribe_audio` 方法。")


class MlxWhisperProcessor(BaseAudioProcessor):
    """基於 Apple 官方 mlx-whisper 的極速處理器（專為 M 系列晶片最佳化）。"""

    def __init__(self, model_name: str) -> None:
        self.mlx_whisper = _try_import_mlx_whisper()
        if self.mlx_whisper is None:
            raise ImportError("請先安裝 `mlx-whisper`：pip install mlx-whisper")
        super().__init__(model_name)
        log.info("⚡️ [MlxWhisper] 專為 Apple Silicon 加速的 Whisper 引擎")

    def transcribe_audio(self, audio_path: str) -> Tuple[str, list]:
        with timer(f"[MlxWhisper] 轉錄 {Path(audio_path).name}"):
            log.info("🎵 [MlxWhisper] 處理: %s", Path(audio_path).name)
            log.info("🔄 正在執行語音轉錄...")

            try:
                # mlx_whisper 封裝了讀取與轉錄，直接傳入檔案路徑
                result = self.mlx_whisper.transcribe(
                    audio_path, path_or_hf_repo=self.model_name
                )
            except TypeError as e:
                # Some repositories (like openai/whisper-large-v3) do not have the expected MLX weights format
                # (they lack generation_config or specific MLX structure), causing model load to fail in MLX.
                log.error(
                    "❌ MlxWhisper 載入模型失敗，該模型可能尚未轉換為 MLX 專用格式。"
                )
                log.warning("⚠️ 建議改用 `mlx-community/whisper-large-v3-turbo`。")
                log.debug("詳細錯誤: %s", e)
                raise RuntimeError("MlxWhisper 模型不相容目前引擎。") from e
            except Exception as e:
                log.error("❌ MlxWhisper 轉錄發生未知錯誤: %s", e)
                raise RuntimeError("MlxWhisper 轉錄失敗。") from e

            transcribed_text = result.get("text", "").strip()
            chunks: list[dict] = []
            if "segments" in result:
                for seg in result["segments"]:
                    chunks.append(
                        {
                            "timestamp": (seg.get("start", 0.0), seg.get("end", 0.0)),
                            "text": seg.get("text", "").strip(),
                            "speaker": None,
                        }
                    )
        return transcribed_text, chunks


class FunASRProcessor(BaseAudioProcessor):
    """基於阿里巴巴 FunASR 的中文語音識別處理器（整合 V2 量化 + V3.1 邏輯）。"""

    def __init__(self, model_name: str, quantize: str = "int8") -> None:
        AutoModel = _try_import_funasr()
        if AutoModel is None:
            raise ImportError(
                '請先安裝 `funasr`：pip install "funasr[runtime]" modelscope '
                "-f https://modelscope.oss-cn-beijing.aliyuncs.com/releases/repo.html"
            )
        super().__init__(model_name)

        with timer("FunASR 模型初始化"):
            # SenseVoiceSmall 的官方長音訊流程：VAD + 標點 + 說話人。
            # FunASR 目前對 MPS 支援不完整；Apple Silicon 退回 CPU，避免啟動時直接失敗。
            model_device = self.device if self.device in {"cuda", "cpu"} else "cpu"
            model_kwargs: dict = {"model": model_name, "device": model_device}
            is_sensevoice = "sensevoice" in model_name.lower()
            if is_sensevoice:
                model_kwargs.update(
                    {
                        "vad_model": "fsmn-vad",
                        "vad_kwargs": {"max_single_segment_time": 30000},
                        "punc_model": "ct-punc",
                        "spk_model": "cam++",
                    }
                )
                log.info("🎙️ [FunASR] 啟用 VAD、標點與 CAM++ 說話人辨識")
            if quantize and quantize.lower() != "none":
                # FunASR 的 Python 推論不一定接受 quantize 參數；量化模型應改用 ONNX/GGUF。
                log.info(
                    "⚙️ [FunASR] 量化偏好: %s（Python 推論使用模型原生精度）", quantize
                )
            else:
                log.info("⚙️ [FunASR] 未啟用量化，使用預設精度。")

            log.info("⚡️ [FunASR] 使用設備: %s", model_device.upper())
            self.model = AutoModel(**model_kwargs)

    def transcribe_audio(self, audio_path: str) -> Tuple[str, list]:
        with timer(f"[FunASR] 轉錄 {Path(audio_path).name}"):
            log.info("🎵 [FunASR] 處理: %s", Path(audio_path).name)
            log.info("🔄 正在執行語音轉錄...")
            try:
                result = self.model.generate(
                    input=audio_path,
                    cache={},
                    language="auto",
                    use_itn=True,
                    batch_size_s=60,
                    merge_vad=True,
                    merge_length_s=15,
                )
            except Exception as e:
                log.error("❌ [FunASR] 轉錄失敗: %s", e)
                raise RuntimeError("FunASR 轉錄失敗。") from e

            text = _clean_asr_text(result[0].get("text", "") if result else "")
            chunks: list[dict] = []
            if result and "sentence_info" in result[0]:  # SenseVoice 格式
                for s in result[0]["sentence_info"]:
                    chunks.append(
                        {
                            "timestamp": (
                                s.get("start", 0) / 1000.0,
                                s.get("end", 0) / 1000.0,
                            ),
                            "speaker": s.get("spk"),
                            "text": s.get("text", ""),
                        }
                    )
            elif result and "timestamp" in result[0]:  # Paraformer 格式
                for ts in result[0]["timestamp"]:
                    chunks.append(
                        {
                            "timestamp": (ts[0] / 1000.0, ts[1] / 1000.0),
                            "speaker": None,
                            "text": ts[2],
                        }
                    )
        return text, chunks


# ═══════════════════════════════════════════════════════════════════════════════
# 🏭 工廠函數
# ═══════════════════════════════════════════════════════════════════════════════

_ENGINE_MAP = {
    "mlx_whisper": lambda cfg: MlxWhisperProcessor(cfg.whisper_model),
    "funasr": lambda cfg: FunASRProcessor(cfg.funasr_model, cfg.funasr_quantize),
}


def create_processor(config: AppConfig) -> BaseAudioProcessor:
    """根據設定建立對應的 ASR 處理器。"""
    factory = _ENGINE_MAP.get(config.asr_engine)
    if factory is None:
        raise ValueError(
            f"❌ 未知的 ASR 引擎 '{config.asr_engine}'。"
            f"可用選項: {', '.join(_ENGINE_MAP.keys())}"
        )
    return factory(config)


# ═══════════════════════════════════════════════════════════════════════════════
# 📝 摘要 Prompt 風格集（含 V3.1 DSPy 結構化 + 多種優化版供選擇）
# ═══════════════════════════════════════════════════════════════════════════════

PROMPT_STYLES: dict[str, dict[str, str]] = {
    # ── 1. 詳細結構化（原版 V3.1 DSPy 風格，增強版）──
    "detailed": {
        "name": "📋 正式會議紀錄（Decision Ready）",
        "description": "完整整理基本資料、結論、決議、待辦、風險與未決問題；不推測缺漏資訊。",
        "template": """\
# Role: 資深會議紀錄與決策追蹤專家

# Task
將逐字稿整理為可供主管快速決策、團隊直接追蹤的正式會議紀錄。先依議題整併內容，再判斷每項資訊是已決議、提案、討論中或待確認。刪除口頭禪與重複內容，但不可改變原意。

# Output Format (Strict Markdown)

### 📅 會議紀錄：[可確認的會議主題；否則填「未提供」]

**0. 基本資料**
- 日期／時間：[未提供時明確標示]
- 參與者：[僅列逐字稿可確認者]
- 會議目的：[1 句]
- 摘要可信度：[高／中／低，依逐字稿完整度判斷]

**1. 一頁摘要**
- **核心結論：** [1-3 點]
- **主要進展：** [1-3 點]
- **最大風險／阻塞：** [1-3 點]
- **下一步：** [1-3 點]

**2. 已確認決議**
| 決議內容 | 狀態 | 依據／條件 | 影響範圍 |
| :--- | :--- | :--- | :--- |
| [只列明確達成共識或拍板的內容] | 已決議 | [關鍵條件；無則填未提供] | [無則填未提供] |

若沒有明確決議，寫「本次無可確認的正式決議」。

**3. 議題討論**
- **[議題名稱]**
  - 背景／問題：...
  - 主要觀點：[標註可確認的發言者]
  - 共識：...
  - 分歧：...
  - 狀態：[已決議／討論中／待確認]

**4. 待辦事項**
| 優先級 | 負責人 | 可執行任務 | 期限 | 完成標準 |
| :---: | :--- | :--- | :--- | :--- |
| [高／中／低／未標示] | [姓名／未指定] | [動詞開頭的具體任務] | [日期／未提供] | [逐字稿未提則填未提供] |

**5. 風險與阻塞**
| 項目 | 影響 | 因應方式 | 負責人 |
| :--- | :--- | :--- | :--- |
| ... | ... | [未提供時不得自行提出] | [姓名／未指定] |

**6. 未決問題／待確認**
- [尚未取得共識、資料不足或需外部確認的事項]

**7. 下次追蹤**
- 建議追蹤時間：[逐字稿有提才填，否則未提供]
- 必須回報項目：...

---

# Input Text
{text}""",
    },
    # ── 2. 精簡重點版 ──
    "concise": {
        "name": "⚡ 精簡重點（Quick Summary）",
        "description": "快速抓出重點，適合站立會議、短促的進度同步。輸出短而精準。",
        "template": """\
# Role: 會議速記員

# Task
你需要在 200 字以內快速整理出會議的核心內容。簡短、精準、不廢話。

# Output Format (Strict Markdown)

### ⚡ 快速摘要

**主題**：[一句話概括]

**重點決定**：
1. ...
2. ...

**待辦**：
- [ ] [誰] → [做什麼] (期限)

**下次要追蹤**：
- ...

---

# Input Text
{text}""",
    },
    # ── 3. 逐條行動導向版 ──
    "action": {
        "name": "🎯 行動導向（Action-Focused）",
        "description": "以「誰做什麼、何時完成」為核心。適合專案追蹤型會議。",
        "template": """\
# Role: 專案管理助理

# Task
你的唯一目標是從會議逐字稿中提取所有 **可執行的行動項目 (Action Items)**。忽略閒聊與背景討論，專注於「承諾」和「指派」。

# Extraction Rules
1. 提取所有明確承諾、指派或下一步；沒有負責人時填「未指定」，不得推測。
2. 期限只採用逐字稿明確資訊；沒有期限時填「未提供」。
3. 優先級只有在逐字稿有明確急迫性時才標示，否則填「未標示」。
4. 同時列出阻塞、依賴條件及尚待確認的資訊。

# Output Format (Strict Markdown)

### 🎯 行動項目清單

**會議背景**：[2-3 句話]

| 優先級 | 負責人 | 行動項目 | 期限 | 備註 |
| :---: | :--- | :--- | :--- | :--- |
| 🔴 | [姓名] | [做什麼] | [何時] | [補充] |
| 🟡 | ... | ... | ... | ... |

**⚠️ 風險/阻塞項目**：
- ...

---

# Input Text
{text}""",
    },
    # ── 4. 訪談 / 一對一對話版 ──
    "interview": {
        "name": "🎤 訪談紀錄（Interview / 1-on-1）",
        "description": "適合訪談、面談、Podcast 等「對話型」錄音。按主題歸納發言，保留觀點原味。",
        "template": """\
# Role: 資深訪談整理師

# Task
將一段對話或訪談的逐字稿整理為結構化的訪談紀錄。保留原始觀點的語氣和細節，但去除口語的「嗯」、「呃」、重複等雜訊。

# Output Format (Strict Markdown)

### 🎤 訪談紀錄：[自動生成標題]

**參與者**：[根據語境辨識]
**日期/時長**：[如可判斷]

---

**主題一：[標題]**
> 💬 [發言者 A]：「[整理後的核心觀點，保留原意]」
>
> 💬 [發言者 B]：「[回應/補充]」
>
> 📝 **小結**：...

**主題二：[標題]**
> ...

---

**🔑 Key Takeaways（關鍵洞察）**
1. ...
2. ...

**💡 精彩語錄 (Notable Quotes)**
- 「...」— [發言者]

---

# Input Text
{text}""",
    },
    # ── 5. 腦暴 / 創意發想版 ──
    "brainstorm": {
        "name": "💡 腦暴整理（Brainstorm Organizer）",
        "description": "適合腦力激盪、創意發想。將發散的點子歸類、合併、評估可行性。",
        "template": """\
# Role: 創意策略整理師

# Task
從一場腦力激盪會議的逐字稿中，提取所有提出的點子和創意，進行歸類、去重、並評估初步可行性。

# Output Format (Strict Markdown)

### 💡 腦暴成果整理：[主題]

**會議概覽**：
> [1-2 句描述這場腦暴的目標和氛圍]

**🌟 點子分類**

| 類別 | 點子描述 | 提出者 | 可行性 | 備註 |
| :--- | :--- | :--- | :---: | :--- |
| [類別名] | [點子] | [姓名] | ⭐⭐⭐ | [補充] |

**🏆 Top 3 最具潛力的點子**
1. **[點子名稱]**：[為什麼值得優先推進？]
2. ...
3. ...

**🗑️ 被否決或擱置的點子**
- [點子]：[原因]

**📌 下一步**
- ...

---

# Input Text
{text}""",
    },
    # ── 6. 原版簡易 Prompt（來自原版 & V1.1 的經典格式）──
    "classic": {
        "name": "📝 經典簡易（Classic Simple）",
        "description": "最基礎的條列式摘要。適合快速場景或不需要複雜格式的情況。",
        "template": """\
請將以下會議內容進行專業、條理分明的總結。提取出主要的討論要點、決議事項和待辦事項，並以點列式呈現：

{text}""",
    },
}


def list_prompt_styles() -> None:
    """列出所有可用的 Prompt 風格。"""
    print("\n📝 可用的摘要 Prompt 風格：\n")
    print(f"  {'KEY':<13} {'名稱':<35} 說明")
    print("  " + "─" * 88)
    for key, info in PROMPT_STYLES.items():
        print(f"  {key:<13} {info['name']:<33} {info['description']}")
    print()
    print("  使用方式：python transcribe_pro.py --prompt-style <KEY>")
    print("  預設風格：detailed\n")


def get_summary_prompt(style: str, text: str) -> str:
    """取得指定風格的摘要 Prompt。"""
    if style not in PROMPT_STYLES:
        log.warning("⚠️ 未知的 Prompt 風格 '%s'，改用 'detailed'。", style)
        style = "detailed"
    template = PROMPT_STYLES[style]["template"]
    log.info("📝 使用摘要風格: %s", PROMPT_STYLES[style]["name"])
    rendered_prompt = template.format(text=text)
    return apply_summary_rules(rendered_prompt)


# ═══════════════════════════════════════════════════════════════════════════════
# 🤖 Gemini 文字摘要（整合 V3 最新模型 + 重試邏輯）
# ═══════════════════════════════════════════════════════════════════════════════


def summarize_with_gemini(text: str, config: AppConfig) -> str:
    """使用 Google GenAI SDK 進行結構化會議摘要。"""
    config.load_api_key_from_config()
    if not config.gemini_api_key:
        log.warning("⚠️ 未設定 GEMINI_API_KEY，跳過摘要。")
        return "摘要功能未啟用，因為缺少 API 金鑰。"

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        log.error("❌ 缺少 google-genai，請安裝 `pip install google-genai`。")
        return "❌ 摘要功能缺少 google-genai 套件。"

    prompt = get_summary_prompt(config.prompt_style, text)
    log.info("☁️ 正在使用 Gemini 模型 %s 進行摘要分析...", config.gemini_model)

    # 重試邏輯
    max_retries = 2
    for attempt in range(1, max_retries + 1):
        try:
            with timer("文字摘要 (Gemini)"):
                client = genai.Client(api_key=config.gemini_api_key)
                response = client.models.generate_content(
                    model=config.gemini_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.2),
                )
                return response.text
        except Exception as e:
            if attempt < max_retries:
                log.warning("⚠️ 摘要失敗 (第 %d 次)，重試中... 錯誤: %s", attempt, e)
                time.sleep(2)
            else:
                log.error("❌ 摘要最終失敗: %s", e)
                return f"生成摘要時發生錯誤: {e}"

    return "❌ 摘要失敗。"


def summarize_with_ollama(text: str, config: AppConfig) -> str:
    """使用 Ollama 地端 LLM 進行結構化會議摘要。"""
    import requests

    prompt = get_summary_prompt(config.prompt_style, text)
    api_url = f"{config.ollama_base_url}/api/generate"

    log.info("🏠 正在使用 Ollama 地端模型進行摘要分析...")
    log.info("🏠 模型: %s", config.ollama_model)

    try:
        with timer(f"文字摘要 (Ollama/{config.ollama_model})"):
            response = requests.post(
                api_url,
                json={
                    "model": config.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,  # 低溫度確保摘要穩定
                        "num_predict": 4096,  # 足夠生成完整摘要
                        "top_p": 0.9,
                    },
                },
                timeout=300,  # 地端模型可能需較長時間
            )
            response.raise_for_status()
            result = response.json()
            return result.get("response", "❌ Ollama 回應為空。").strip()
    except requests.ConnectionError:
        log.error(
            "❌ 無法連線至 Ollama 服務 (%s)。請確認 Ollama 已啟動。",
            config.ollama_base_url,
        )
        return "❌ Ollama 服務未啟動或無法連線。請先執行 `ollama serve`。"
    except requests.Timeout:
        log.error("❌ Ollama 回應逾時。")
        return "❌ Ollama 回應逾時，請嘗試較小的模型或較短的逐字稿。"
    except Exception as e:
        log.error("❌ Ollama 摘要失敗: %s", e)
        return f"❌ 地端摘要生成錯誤: {e}"


def summarize_text(text: str, config: AppConfig) -> str:
    """根據設定選擇雲端或地端引擎進行會議摘要。"""
    if not text.strip():
        log.warning("⚠️ 逐字稿為空，跳過摘要。")
        return "逐字稿內容為空，無法生成摘要。"

    if config.summary_engine == "ollama":
        return summarize_with_ollama(text, config)
    else:
        return summarize_with_gemini(text, config)


# ═══════════════════════════════════════════════════════════════════════════════
# 🔄 核心處理流程（整合原版 Google Drive 流程 + V1.1 格式驗證）
# ═══════════════════════════════════════════════════════════════════════════════


def process_audio_file(
    audio_path: str,
    audio_processor: BaseAudioProcessor,
    config: AppConfig,
    gdrive_manager: Optional[GoogleDriveManager] = None,
) -> dict[str, Path]:
    """處理單一音訊檔案：（可選下載）→ 格式驗證 → 轉錄 → 摘要 → 儲存（→ 可選上傳）。"""
    path = Path(audio_path)
    if not path.exists():
        log.error("❌ 找不到檔案: %s", audio_path)
        return

    # 格式驗證（來自 V1.1）
    if not validate_audio_format(audio_path):
        raise ValueError(f"不支援的音訊格式: {Path(audio_path).suffix}")

    transcribed_text, chunks = audio_processor.transcribe_audio(audio_path)
    transcribed_text = _clean_asr_text(transcribed_text)
    summary = summarize_text(transcribed_text, config)

    # 建立輸出目錄
    output_dir = config.output_dir / path.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / f"{path.stem}_會議摘要.txt"

    artifacts = write_transcription_artifacts(
        output_dir, path.stem, transcribed_text, chunks
    )
    for artifact_path in artifacts.values():
        log.info("💾 輸出已儲存: %s", artifact_path)

    summary_path.write_text(summary, encoding="utf-8")
    log.info("💾 摘要已儲存: %s", summary_path)
    artifacts["summary"] = summary_path

    # Google Drive 上傳（來自原版）
    if gdrive_manager and gdrive_manager.service:
        log.info("📤 正在上傳結果至 Google Drive...")
        for artifact_path in artifacts.values():
            gdrive_manager.upload(
                str(artifact_path), config.gdrive_upload_folder_id or None
            )

    # 列印結果
    print(f"\n{'=== 轉錄結果 ===':=^60}")
    print(artifacts["transcript"].read_text(encoding="utf-8"))
    print(f"\n{'=== 會議摘要 ===':=^60}")
    print(summary)
    return artifacts


def process_gdrive_file(
    file_id: str,
    audio_processor: BaseAudioProcessor,
    config: AppConfig,
) -> None:
    """處理 Google Drive 上的音訊檔案（來自原版）。"""
    gdrive = GoogleDriveManager()
    if not gdrive.authenticate():
        return

    temp_path = Path(tempfile.mktemp(suffix=".tmp", prefix=f"gdrive_{file_id}_"))
    try:
        if not gdrive.download(file_id, str(temp_path)):
            return
        process_audio_file(
            str(temp_path), audio_processor, config, gdrive_manager=gdrive
        )
    finally:
        temp_path.unlink(missing_ok=True)
        log.info("🗑️ 已清理暫存下載檔案。")


def batch_process_folder(
    folder_path: str,
    audio_processor: BaseAudioProcessor,
    config: AppConfig,
) -> None:
    """批次處理資料夾內所有音訊檔案。"""
    folder = Path(folder_path)
    if not folder.is_dir():
        log.error("❌ 資料夾不存在: %s", folder_path)
        return

    audio_files: List[Path] = sorted(
        f
        for f in folder.iterdir()
        if f.suffix.lower() in SUPPORTED_EXTENSIONS and not f.name.startswith(".")
    )

    if not audio_files:
        log.error("❌ 在 %s 中找不到支援的音訊檔案。", folder_path)
        log.info("📋 支援格式: %s", ", ".join(sorted(SUPPORTED_EXTENSIONS)))
        return

    total = len(audio_files)
    log.info("📁 找到 %d 個音訊檔案，開始批次處理...", total)

    success_count = 0
    fail_count = 0
    total_batch_start = time.time()

    for i, file_path in enumerate(audio_files, 1):
        pct = (i / total) * 100
        print(f"\n{'=' * 70}")
        log.info("🔄 處理第 %d/%d 個檔案 (%.1f%%): %s", i, total, pct, file_path.name)
        print(f"{'=' * 70}")

        file_start = time.time()
        try:
            process_audio_file(str(file_path), audio_processor, config)
            success_count += 1
        except Exception as e:
            log.error("❌ 處理 %s 時發生錯誤: %s", file_path.name, e)
            fail_count += 1
        finally:
            log.info(
                "📄 '%s' 處理完成，耗時: %s",
                file_path.name,
                format_duration(time.time() - file_start),
            )

    # 批次處理統計
    total_elapsed = time.time() - total_batch_start
    print(f"\n{'=' * 70}")
    log.info("📊 批次處理統計:")
    log.info("   ✅ 成功: %d 個", success_count)
    if fail_count:
        log.info("   ❌ 失敗: %d 個", fail_count)
    log.info("   ⏱️ 總耗時: %s", format_duration(total_elapsed))
    print(f"{'=' * 70}")


def interactive_mode(audio_processor: BaseAudioProcessor, config: AppConfig) -> None:
    """交互式模式：手動選擇操作（整合 V1.1 的 Google Drive 選項 + 摘要風格切換）。"""
    while True:
        print(f"\n{'=' * 50}")
        print("  請選擇操作：")
        print("  1. 輸入本地檔案路徑進行處理")
        if config.enable_gdrive:
            print("  2. 輸入 Google Drive 檔案 ID 進行處理")
        print("  3. 切換摘要 Prompt 風格")
        print("  4. 退出程式")
        print(f"{'=' * 50}")

        try:
            choice = input("請輸入選項: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 再見！")
            break

        if choice == "1":
            try:
                file_path = input("請輸入音訊檔案路徑: ").strip()
            except (EOFError, KeyboardInterrupt):
                continue
            if file_path and Path(file_path).exists():
                process_audio_file(file_path, audio_processor, config)
            else:
                log.error("❌ 檔案路徑無效或不存在。")

        elif choice == "2" and config.enable_gdrive:
            try:
                file_id = input("請輸入 Google Drive 檔案 ID: ").strip()
            except (EOFError, KeyboardInterrupt):
                continue
            if file_id:
                process_gdrive_file(file_id, audio_processor, config)
            else:
                log.error("❌ 檔案 ID 無效。")

        elif choice == "3":
            list_prompt_styles()
            try:
                new_style = input("請輸入要使用的風格 KEY: ").strip()
            except (EOFError, KeyboardInterrupt):
                continue
            if new_style in PROMPT_STYLES:
                config.prompt_style = new_style
                log.info("✅ 已切換至: %s", PROMPT_STYLES[new_style]["name"])
            else:
                log.error("❌ 無效的風格 KEY。")

        elif choice == "4":
            print("👋 感謝使用！再見！")
            break
        else:
            log.error("❌ 無效的選項。")


# ═══════════════════════════════════════════════════════════════════════════════
# 🚀 命令列介面 & 進入點
# ═══════════════════════════════════════════════════════════════════════════════


def parse_args() -> AppConfig:
    """解析命令列參數並生成 AppConfig。"""
    parser = argparse.ArgumentParser(
        description="🎤 會議錄音轉錄 & 結構化摘要工具 (優化整合版)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
範例:
  %(prog)s --mode batch --folder /path/to/audios
  %(prog)s --mode single --file meeting.m4a --prompt-style action
  %(prog)s --mode single --file meeting.m4a --engine funasr
  %(prog)s --enable-gdrive --gdrive-id FILE_ID
  %(prog)s --list-prompts
        """,
    )
    # ASR 引擎
    parser.add_argument(
        "--engine",
        default="funasr",
        choices=list(_ENGINE_MAP.keys()),
        help="ASR 語音識別引擎 (預設 ⭐推薦: funasr)",
    )
    parser.add_argument(
        "--model",
        default="mlx-community/whisper-large-v3-turbo",
        help="MLX Whisper 模型 (預設: mlx-community/whisper-large-v3-turbo)",
    )
    parser.add_argument(
        "--funasr-model",
        default="iic/SenseVoiceSmall",
        help="FunASR 模型 (預設: iic/SenseVoiceSmall)",
    )
    parser.add_argument(
        "--funasr-quantize",
        default="int8",
        help="FunASR 量化: none|int8|fp16 (預設: int8)",
    )

    # 摘要引擎
    parser.add_argument(
        "--summary-engine",
        default="gemini",
        choices=["gemini", "ollama"],
        help="摘要引擎：gemini (雲端) 或 ollama (地端) (預設: gemini)",
    )
    parser.add_argument(
        "--gemini-model",
        default="gemini-3.5-flash",
        help="Gemini 模型 ID (預設: gemini-3.5-flash)",
    )
    parser.add_argument(
        "--ollama-model",
        default="qwen2.5:7b",
        help="Ollama 地端模型 (預設 ⭐推薦: qwen2.5:7b)",
    )
    parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="Ollama API 位址 (預設: http://localhost:11434)",
    )

    # 處理模式
    parser.add_argument(
        "--mode",
        default="batch",
        choices=["single", "batch", "interactive"],
        help="處理模式 (預設: batch)",
    )
    parser.add_argument("--file", default="", help="單檔模式的音訊檔案路徑")
    parser.add_argument(
        "--folder", default="/Users/jy/Downloads", help="批次模式的資料夾路徑"
    )
    parser.add_argument(
        "--output", default="./output", help="輸出目錄 (預設: ./output)"
    )

    # 摘要
    parser.add_argument(
        "--prompt-style",
        default="detailed",
        choices=list(PROMPT_STYLES.keys()),
        help="摘要 Prompt 風格 (預設: detailed)",
    )
    parser.add_argument(
        "--list-prompts", action="store_true", help="列出所有可用的摘要 Prompt 風格"
    )

    # Google Drive
    parser.add_argument(
        "--enable-gdrive", action="store_true", help="啟用 Google Drive 整合功能"
    )
    parser.add_argument(
        "--gdrive-id",
        default="",
        help="Google Drive 檔案 ID（搭配 --enable-gdrive 使用）",
    )

    args = parser.parse_args()

    if args.list_prompts:
        list_prompt_styles()
        sys.exit(0)

    return AppConfig(
        asr_engine=args.engine,
        whisper_model=args.model,
        mode=args.mode,
        single_file=args.file,
        batch_folder=args.folder,
        output_dir=Path(args.output),
        prompt_style=args.prompt_style,
        summary_engine=args.summary_engine,
        gemini_model=args.gemini_model,
        ollama_model=args.ollama_model,
        ollama_base_url=args.ollama_url,
        funasr_model=args.funasr_model,
        funasr_quantize=args.funasr_quantize,
        enable_gdrive=args.enable_gdrive,
        gdrive_file_id=args.gdrive_id,
    )


def main() -> None:
    """程式主進入點。"""
    # 設定 torchaudio backend（含 V1.1 的 fallback）
    setup_torchaudio_backend()

    config = parse_args()

    print("🎤 會議記錄自動化工具 (Pro Edition) 🎤")
    print("=" * 55)
    log.info("📋 當前設定:")
    log.info("   引擎: %s", config.asr_engine)
    if config.asr_engine == "funasr":
        log.info("   模型: %s", config.funasr_model)
    else:
        log.info("   模型: %s", config.whisper_model)
    log.info("   模式: %s", config.mode)
    log.info(
        "   摘要引擎: %s",
        "☁️ Gemini (雲端)"
        if config.summary_engine == "gemini"
        else f"🏠 Ollama (地端: {config.ollama_model})",
    )
    log.info("   摘要風格: %s", PROMPT_STYLES[config.prompt_style]["name"])
    log.info("   輸出目錄: %s", config.output_dir)
    if config.enable_gdrive:
        log.info("   ☁️ Google Drive: 已啟用")
    print("=" * 55)

    # 建立 ASR 處理器
    try:
        processor = create_processor(config)
    except (ImportError, ValueError) as e:
        log.error("❌ 初始化失敗: %s", e)
        log.error("   請確保已安裝對應引擎的套件。")
        sys.exit(1)
    except Exception as e:
        log.error("❌ 初始化時發生未知錯誤: %s", e)
        sys.exit(1)

    # 執行對應模式
    with timer("全部任務"):
        # Google Drive 模式（來自原版）
        if config.gdrive_file_id:
            log.info("☁️ Google Drive 檔案處理模式")
            process_gdrive_file(config.gdrive_file_id, processor, config)

        elif config.mode == "single":
            if not config.single_file:
                log.error("❌ 單檔模式需指定 --file 參數。")
                sys.exit(1)
            log.info("🎵 單檔處理模式")
            process_audio_file(config.single_file, processor, config)

        elif config.mode == "batch":
            log.info("📁 批次處理模式")
            batch_process_folder(config.batch_folder, processor, config)

        elif config.mode == "interactive":
            log.info("💬 交互式模式")
            interactive_mode(processor, config)

    print("\n🎉🎉🎉 程式執行完成！🎉🎉🎉")


if __name__ == "__main__":
    main()
