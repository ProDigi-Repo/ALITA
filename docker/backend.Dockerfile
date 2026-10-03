FROM python:3.12-slim

# LibreOffice nur für alte .doc/.ppt/.xls; mit WITH_LIBREOFFICE=false bauen spart ~500 MB
ARG WITH_LIBREOFFICE=true
RUN if [ "$WITH_LIBREOFFICE" = "true" ]; then \
      apt-get update && apt-get install -y --no-install-recommends libreoffice-writer-nogui libreoffice-impress-nogui libreoffice-calc-nogui \
      && rm -rf /var/lib/apt/lists/*; \
    fi

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
WORKDIR /app/backend
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

RUN useradd --create-home --uid 1000 app && mkdir -p /data && chown app /data
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
