FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY src/ src/
COPY sim/ sim/
COPY workflows/ workflows/
ENV PYTHONUNBUFFERED=1
CMD ["python3", "src/main.py", "--serve"]
