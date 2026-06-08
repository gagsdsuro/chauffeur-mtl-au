FROM python:3.12-slim

WORKDIR /app

# Dépendances système (fonts pour reportlab)
RUN apt-get update && apt-get install -y --no-install-recommends \
        fontconfig \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code source (les données sont montées via volume)
COPY app/      ./app/
COPY scripts/  ./scripts/

EXPOSE 8501

HEALTHCHECK CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app/ui.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
