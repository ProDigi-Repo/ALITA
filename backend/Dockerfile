FROM python:3.12-slim
# LibreOffice nur für alte .doc/.ppt-Dateien; weglassen spart ~500 MB
RUN apt-get update && apt-get install -y --no-install-recommends libreoffice-writer-nogui libreoffice-impress-nogui \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app/backend
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
