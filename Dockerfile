FROM python:3.12-slim
WORKDIR /app
COPY src/ src/
COPY sim/ sim/
ENV PYTHONUNBUFFERED=1
CMD ["python3", "src/main.py", "--serve"]
