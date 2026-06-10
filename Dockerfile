FROM python:3.12-slim

WORKDIR /app

# Dépendances système (fonts pour reportlab)
RUN apt-get update && apt-get install -y --no-install-recommends \
        fontconfig \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Utilisateur non-root aligné sur l'hôte (UID/GID configurables au build).
# Évite que les fichiers écrits dans le volume ./data appartiennent à root.
ARG UID=1000
ARG GID=1000
RUN groupadd -g ${GID} app \
    && useradd -u ${UID} -g ${GID} -m -s /bin/bash app

# Code source (les données sont montées via volume)
COPY app/      ./app/
COPY scripts/  ./scripts/

USER app

EXPOSE 8501

HEALTHCHECK CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app/ui.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
