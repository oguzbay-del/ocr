# Unlimited-OCR web UI for Cloud Run (NVIDIA L4). Model weights are baked into the image.
FROM pytorch/pytorch:2.10.0-cuda12.6-cudnn9-runtime

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/tmp/hf \
    MODEL_DIR=/model

RUN pip install "transformers==4.57.1" "gradio>=5,<6" einops addict easydict pymupdf matplotlib accelerate

# model.safetensors is a byte-identical copy of the shard listed in the index; skip it and the docs.
RUN python -c "from huggingface_hub import snapshot_download; \
snapshot_download('Oguzbayrakdar/Unlimited-OCR', local_dir='/model', \
ignore_patterns=['model.safetensors', 'assets/*', 'wheel/*', '*.pdf'])"

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

WORKDIR /app
COPY app.py .
CMD ["python", "app.py"]
