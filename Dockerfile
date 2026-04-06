FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py db.py osm.py routes_auth.py routes_admin.py routes_api.py seed_stasjoner.py ./
COPY public/ ./public/

EXPOSE 3002

CMD ["sh", "-c", "gunicorn -w 1 --threads 4 -b 0.0.0.0:${PORT:-7342} server:app"]
