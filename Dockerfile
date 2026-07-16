FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models/huggingface \
    MODELSCOPE_CACHE=/models/modelscope

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements-oci.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements-oci.txt

COPY transcribe_pro.py webui.py asr_catalog.py summary_prompt_rules.py README.md ./
COPY .streamlit/config.toml ./.streamlit/config.toml

RUN useradd --create-home --uid 10001 app \
    && mkdir -p /models /app/output \
    && chown -R app:app /models /app
USER app

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3)"

CMD ["streamlit", "run", "webui.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
