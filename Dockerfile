FROM python:3.12-slim

WORKDIR /app

COPY app.py .

RUN pip install --no-cache-dir fastapi uvicorn

EXPOSE 7777

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7777"]
