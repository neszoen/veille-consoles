# Pour faire tourner la veille sur un VPS ou un Raspberry Pi (optionnel).
#   docker build -t veille .
#   docker run -d --restart unless-stopped --env-file .env -v "$PWD/data:/app/data" veille
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "-m", "veille", "--boucle", "30"]
