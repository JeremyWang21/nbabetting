FROM python:3.12-slim

WORKDIR /app

# System deps for asyncpg + pdfplumber
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# chmod before user switch so it runs as root
RUN chmod +x /app/scripts/start.sh

# Run as non-root
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["/app/scripts/start.sh"]
