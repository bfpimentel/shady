FROM docker.io/library/python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY app.py ./
COPY templates/ ./templates/
COPY assets/ ./assets/

RUN pip install .

RUN mkdir -p /app/uploads
RUN mkdir -p /app/config

EXPOSE 7111

CMD ["python", "app.py"]
