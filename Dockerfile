FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    FSS_LICENSE_DATABASE=/data/licenses.sqlite3

WORKDIR /app
RUN pip install --no-cache-dir "cryptography>=43.0.0"
COPY src/face_swap_studio/__init__.py src/face_swap_studio/__init__.py
COPY src/face_swap_studio/licensing src/face_swap_studio/licensing
RUN mkdir -p /data && useradd --system --uid 10001 --create-home fss && chown -R fss:fss /app /data

USER fss
EXPOSE 8787
CMD ["python", "-m", "face_swap_studio.licensing.server"]
