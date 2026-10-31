# Mettre à jour le tag ET l'empreinte lors d'une mise à jour de Python.
FROM python:3.12.16-slim@sha256:8523d6abeb48ceae0b7240d30c5808fc26cb79c1a635bacdf19cf3baecfbec07

WORKDIR /app

# Dépendances système (fonts pour reportlab)
RUN apt-get update && apt-get install -y --no-install-recommends \
        fontconfig \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.txt \
    && python -m pip check

# Utilisateur non-root aligné sur l'hôte (UID/GID configurables au build).
# Évite que les fichiers écrits dans le volume ./data appartiennent à root.
ARG UID=1000
ARG GID=1000
RUN groupadd -g ${GID} app \
    && useradd -u ${UID} -g ${GID} -m -s /bin/bash app

# Code source (les données sont montées via volume)
COPY app/        ./app/
COPY scripts/    ./scripts/
COPY chauffeur/  ./chauffeur/

USER app

EXPOSE 8501

# Sonde via Python (toujours présent) — l'image slim n'inclut pas curl.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python3", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8501/_stcore/health').read()==b'ok' else 1)"]

CMD ["streamlit", "run", "app/main.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
