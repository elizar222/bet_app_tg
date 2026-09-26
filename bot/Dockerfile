FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN rm -rf wheels tools .venv && mkdir -p data

# на сервере мини-апп слушает все интерфейсы внутри контейнера, HTTPS даёт Caddy
ENV WEB_HOST=0.0.0.0 WEB_PORT=8080
EXPOSE 8080
CMD ["python", "run.py"]
