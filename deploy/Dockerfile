# claude-lit-workflow 網頁服務映像
#
#   docker build -f deploy/Dockerfile -t claude-lit-web .
#   docker run -p 8000:8000 -e WEB_API_TOKEN=... -e GOOGLE_API_KEY=... -v lit-data:/data claude-lit-web
#
# 模板覆蓋：把自訂 templates/ 或 config/ 掛載到 /app/templates、/app/config（cwd 覆蓋機制）。

FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    WEB_DATA_DIR=/data

WORKDIR /app

# 先裝依賴（原始碼變動時可沿用此層快取）
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --extra web --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev --extra web

RUN useradd --create-home --uid 1000 lit \
    && mkdir -p /data \
    && chown lit:lit /data /app
USER lit

VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"

# 驗證設定（WEB_API_TOKEN 或 WEB_TRUST_PROXY_AUTH=1）缺漏時 web 會拒絕以 0.0.0.0 啟動
CMD ["uv", "run", "--no-sync", "web", "--host", "0.0.0.0", "--port", "8000"]
