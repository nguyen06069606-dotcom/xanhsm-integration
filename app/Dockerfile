FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY core ./core
COPY templates ./templates
COPY worker.py monitor.py dashboard.py ./
RUN useradd -r -u 1000 app && chown -R app /srv
USER app
