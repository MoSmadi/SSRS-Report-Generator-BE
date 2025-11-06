# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Install system dependencies for ODBC and build tools.
RUN apt-get update \
    && apt-get install -y curl gnupg unixodbc unixodbc-dev gcc \
    && rm -rf /var/lib/apt/lists/*
# Uncomment the section below and follow Microsoft docs if you need msodbcsql18.
# RUN curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - \
#     && curl https://packages.microsoft.com/config/debian/12/prod.list > /etc/apt/sources.list.d/microsoft.list \
#     && apt-get update && ACCEPT_EULA=Y apt-get install -y msodbcsql18

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV UVICORN_WORKERS=2

CMD ["uvicorn", "app.main:app", "--host", "${SERVER_HOST:-0.0.0.0}", "--port", "${SERVER_PORT:-8000}"]
