FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py db.py osm.py ./
COPY public/ ./public/

EXPOSE 3002

CMD ["python3", "server.py"]
