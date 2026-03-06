FROM python:3.12-slim
WORKDIR /app

RUN pip install --no-cache-dir \
    "agentctx[server] @ https://github.com/aiconceptsonline/agentctx/releases/download/v0.1.1/agentctx-0.1.1-py3-none-any.whl"

COPY main.py .

EXPOSE 8001
CMD ["python", "main.py"]
