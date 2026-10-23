FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr poppler-utils && rm -rf /var/lib/apt/lists/*
COPY requirements.txt pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir --no-deps -e .
COPY examples ./examples
COPY eval ./eval
COPY scripts ./scripts
COPY data ./data
RUN useradd -r -u 10001 extraction && mkdir -p /app/out /app/.cache && chown -R extraction:extraction /app
USER extraction
ENTRYPOINT ["python", "-m", "co_extract"]
CMD ["--help"]
