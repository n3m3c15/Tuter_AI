FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y \
    libgl1 \
    libglx-mesa0 \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

EXPOSE 80

CMD ["uvicorn", "KVerse_chat_main.app:app", "--host", "0.0.0.0", "--port", "80"]
