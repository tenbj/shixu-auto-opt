FROM python:3.11-slim@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 SHIXU_SKIP_DOTENV=true
COPY requirements-lock.txt requirements-lock.txt
RUN pip install --no-cache-dir -r requirements-lock.txt && pip check
RUN groupadd --gid 10001 shixu && useradd --uid 10001 --gid 10001 --no-create-home shixu
COPY app app
COPY static static
COPY docs docs
COPY examples examples
COPY downloads downloads
COPY skills skills
COPY data data
COPY scripts scripts
COPY mcp_server.py mcp_server.py
RUN mkdir -p /app/runtime && chown 10001:10001 /app/runtime && SHIXU_BACKEND=sqlite SHIXU_DB=/tmp/import.sqlite3 python -c "import app.main" && rm -f /tmp/import.sqlite3
USER 10001:10001
EXPOSE 8765
HEALTHCHECK --interval=15s --timeout=10s --start-period=60s --retries=4 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health',timeout=8).read()"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765", "--forwarded-allow-ips", ""]
