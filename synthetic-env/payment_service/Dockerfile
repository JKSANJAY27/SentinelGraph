FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn prometheus-client httpx

COPY main.py .

EXPOSE 8013

CMD ["python", "main.py"]
