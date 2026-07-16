"""ASR 模型目錄與執行環境選擇邏輯。"""

from __future__ import annotations

import platform
from dataclasses import dataclass


@dataclass(frozen=True)
class ASRProfile:
    """一個可在 Web UI 選擇的 ASR 執行設定。"""

    key: str
    label: str
    engine: str
    model: str
    scenario: str
    hardware: str
    memory: str
    accuracy: str
    note: str
    quantize: str = "none"


ASR_PROFILES = {
    "sensevoice_cpu": ASRProfile(
        key="sensevoice_cpu",
        label="SenseVoiceSmall｜OCI／CPU・省資源",
        engine="funasr",
        model="iic/SenseVoiceSmall",
        scenario="中文會議、長時間錄音、多人說話與批次處理",
        hardware="OCI ARM、Linux／Windows CPU、Apple Silicon",
        memory="低～中；適合與其他日常服務共用主機",
        accuracy="中文辨識穩定，速度優先",
        note="支援 VAD 與標點；OCI 穩定模式停用 CAM++ 說話人辨識。",
        quantize="int8",
    ),
    "mlx_whisper_turbo": ASRProfile(
        key="mlx_whisper_turbo",
        label="Whisper Large V3 Turbo｜Mac M4・日常推薦",
        engine="mlx_whisper",
        model="mlx-community/whisper-large-v3-turbo",
        scenario="中文／英文混講、一般會議，兼顧速度與準確度",
        hardware="Apple Silicon；MacBook Air M4 16GB 以上",
        memory="中；模型權重約 1.6GB，執行時占用會再增加",
        accuracy="高；相較完整 Large V3 略降，但速度明顯較快",
        note="Mac M4 24GB 的日常預設，可同時保留瀏覽器與辦公軟體空間。",
    ),
    "mlx_whisper_large_v3_4bit": ASRProfile(
        key="mlx_whisper_large_v3_4bit",
        label="Whisper Large V3 4-bit｜Mac M4・省記憶體實驗",
        engine="mlx_whisper",
        model="mlx-community/whisper-large-v3-mlx-4bit",
        scenario="重要中文錄音、希望使用 Large V3 並降低模型記憶體",
        hardware="Apple Silicon；MacBook Air M4 16GB 以上",
        memory="中；量化權重約 1.0GB，但解碼速度通常慢於 Turbo",
        accuracy="高；4-bit 量化可能帶來少量辨識差異",
        note="建議先用實際會議錄音與 Turbo 比較，再決定是否長期使用。",
    ),
    "mlx_whisper_large_v3": ASRProfile(
        key="mlx_whisper_large_v3",
        label="Whisper Large V3 FP16｜Mac M4・最高精度／高占用",
        engine="mlx_whisper",
        model="mlx-community/whisper-large-v3-mlx",
        scenario="短到中型重要錄音，辨識精度優先於速度與記憶體",
        hardware="Apple Silicon；建議 24GB 以上",
        memory="高；模型權重約 3.1GB，實際執行峰值會更高",
        accuracy="最高，但速度較慢",
        note="MacBook Air M4 24GB 可用；執行前建議關閉大型 IDE、虛擬機等高占用程式。",
    ),
}


def detect_runtime_family(system: str | None = None, machine: str | None = None) -> str:
    """依執行主機判斷後端；從 Mac 瀏覽 OCI 網站仍屬 OCI 環境。"""

    system_name = (system or platform.system()).lower()
    machine_name = (machine or platform.machine()).lower()
    if system_name == "darwin" and machine_name in {"arm64", "aarch64"}:
        return "apple_silicon"
    return "cpu_server"


def available_profile_keys(runtime_family: str | None = None) -> list[str]:
    """只回傳目前執行主機真正能執行的模型。"""

    runtime = runtime_family or detect_runtime_family()
    if runtime == "apple_silicon":
        return [
            "mlx_whisper_turbo",
            "sensevoice_cpu",
            "mlx_whisper_large_v3_4bit",
            "mlx_whisper_large_v3",
        ]
    return ["sensevoice_cpu"]


def default_profile_key(runtime_family: str | None = None) -> str:
    """Mac 預設 Turbo；CPU／OCI 預設 SenseVoice。"""

    runtime = runtime_family or detect_runtime_family()
    return "mlx_whisper_turbo" if runtime == "apple_silicon" else "sensevoice_cpu"


def runtime_label(runtime_family: str | None = None) -> str:
    runtime = runtime_family or detect_runtime_family()
    if runtime == "apple_silicon":
        return "Apple Silicon（本機 MLX 加速）"
    return "CPU／伺服器模式（目前僅顯示可執行模型）"
