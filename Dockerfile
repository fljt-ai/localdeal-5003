FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /data
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 8787
CMD ["python", "-B", "run.py", "--engine", "fastapi", "--container", "--smart-demo", "--db", "/data/localdeal-smart.db"]
