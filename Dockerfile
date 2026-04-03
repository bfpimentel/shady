FROM docker.io/library/python:3.12-slim

WORKDIR /app

COPY . .

RUN pip install .

RUN mkdir -p /app/uploads

EXPOSE 7111

CMD ["python", "app.py"]
