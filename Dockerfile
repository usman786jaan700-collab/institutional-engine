FROM python:3.11-slim
WORKDIR /app
COPY analytics/requirements.txt ./analytics/requirements.txt
RUN pip install --no-cache-dir -r analytics/requirements.txt
COPY . .
CMD ["python", "-m", "analytics.zone_detector"]
