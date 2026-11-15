FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 EARTHPULL_DATA=/data
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY earthpull/ earthpull/

# UI by default. The trend-map job overrides the command.
EXPOSE 8080
CMD ["sh", "-c", "streamlit run earthpull/main.py --server.port ${PORT:-8080} --server.address 0.0.0.0 --server.headless true"]
