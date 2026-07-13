# Astana Hotel AI Call Center — veb server image
# GPU-lu host tələb olunur (nvidia-container-toolkit quraşdırılmalıdır).
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.10 python3-pip ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY knowledge/ knowledge/
COPY database/ database/

# İlk başlanğıcda FAISS indeksi bura yazılacaq
RUN mkdir -p vector_store logs

ENV PYTHONUNBUFFERED=1

EXPOSE 8000
WORKDIR /app/src
CMD ["python3", "-m", "uvicorn", "web.server:app", "--host", "0.0.0.0", "--port", "8000"]
