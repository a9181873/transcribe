#!/bin/bash
# 取得此腳本所在的目錄
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# 指定正確的 Python 路徑（已安裝所有相依套件）
PYTHON="/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"

echo "======================================"
echo "🎤 正在啟動語音識別 Web UI..."
echo "======================================"

# 檢查 streamlit 是否安裝
if ! "$PYTHON" -m streamlit --version &> /dev/null
then
    echo "⚠️ 尚未安裝 streamlit，正在為您安裝..."
    "$PYTHON" -m pip install streamlit
fi

# 啟動 streamlit 應用並開啟瀏覽器
"$PYTHON" -m streamlit run webui.py
