FROM python:3.11-slim
WORKDIR /app
COPY ingestors/requirements.txt ./ingestors/requirements.txt
RUN pip install --no-cache-dir -r ingestors/requirements.txt
COPY . .
CMD ["python", "-m", "ingestors.binance_ingestor"]
