FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY nfe_sync ./nfe_sync
RUN pip install --no-cache-dir . "psycopg[binary]>=3.2"
COPY servico/rodar.py ./rodar.py
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "/app/rodar.py"]
