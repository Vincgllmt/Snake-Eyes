FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Config et sessions de Claude Code dans le volume de données, pour que les
    # conversations survivent à un redémarrage du conteneur.
    CLAUDE_CONFIG_DIR=/app/data/claude

WORKDIR /app

# Le paquet claude-agent-sdk embarque le binaire Claude Code : rien d'autre à installer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
