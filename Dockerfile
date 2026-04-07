FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml .
COPY devgrow/ devgrow/

RUN pip install --no-cache-dir -e .

# Data persists in a named volume mounted at /data
ENV DEVGROW_DATA=/data
VOLUME ["/data"]

EXPOSE 7331

CMD ["devgrow", "serve", "--host", "0.0.0.0", "--port", "7331"]
