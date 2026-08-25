# Taskuary as a container: same UI and API, no Python install on the host.
# Data lives in /data (TASKUARY_HOME). The process binds 0.0.0.0 so Docker can
# reach it; compose publishes that port on 127.0.0.1 by default.
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY taskuary ./taskuary

RUN pip install --no-cache-dir --root-user-action=ignore .
RUN useradd --uid 1000 --create-home --home-dir /home/taskuary taskuary \
 && mkdir -p /data \
 && chown taskuary:taskuary /data

USER taskuary
ENV TASKUARY_HOME=/data \
    TASKUARY_HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 7787
VOLUME /data

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7787/api/health', timeout=4)"

# --no-browser: there is no display in the container. Host/port come from env.
CMD ["taskuary", "--no-browser"]
