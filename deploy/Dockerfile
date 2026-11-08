FROM python:3.13-slim

# Chromium für PDF-Berichte (optional – ohne Chromium entstehen nur HTML-Berichte)
RUN apt-get update && apt-get install -y --no-install-recommends chromium fonts-dejavu-core \
    && apt-get clean
ENV CHROMIUM=/usr/bin/chromium

WORKDIR /app
# Nur für KI_BACKEND=claude nötig; der lokale Betrieb (Ollama) braucht keine Zusatzpakete.
COPY requirements-claude.txt requirements-bilanzen.txt ./
RUN pip install --no-cache-dir -r requirements-claude.txt -r requirements-bilanzen.txt

COPY heizlast ./heizlast
COPY assistent ./assistent
COPY bilanzen ./bilanzen
COPY beispiele ./beispiele
COPY wissen ./wissen
RUN mkdir -p /app/berichte /app/daten && useradd -r -u 10001 ki && chown -R ki /app/berichte /app/daten
USER ki

ENV KI_HOST=0.0.0.0 KI_PORT=8080 BILANZ_HOST=0.0.0.0 BILANZ_PORT=8081 BILANZ_DATENBANK=/app/daten/bilanzen.sqlite BILANZ_CHROMIUM=/usr/bin/chromium PYTHONUNBUFFERED=1
EXPOSE 8080 8081
HEALTHCHECK --interval=30s --timeout=5s CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/gesund', timeout=3).status==200 else 1)"
CMD ["python3", "-m", "assistent"]
