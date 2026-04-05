#!/bin/bash
# 取得此腳本所在的目錄
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "======================================"
echo "🎤 正在啟動語音識別 Web UI..."
echo "======================================"

# 檢查 streamlit 是否安裝
if ! python3 -m streamlit --version &> /dev/null
then
    echo "⚠️ 尚未安裝 streamlit，正在為您安裝..."
    python3 -m pip install streamlit
fi

# 啟動 streamlit 應用並開啟瀏覽器
python3 -m streamlit run webui.py
