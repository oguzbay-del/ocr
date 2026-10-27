"""Gradio web UI for Unlimited-OCR, served on Cloud Run.

The port opens right away and the model loads in the background, so Cloud Run's
startup probe passes; OCR requests wait until the model is ready.
"""
import os
import tempfile
import threading

import gradio as gr
import pymupdf
import torch
from transformers import AutoModel, AutoTokenizer

MODEL_DIR = os.environ.get("MODEL_DIR", "Oguzbayrakdar/Unlimited-OCR")

MODES = {
    "gundam (hızlı)": dict(base_size=1024, image_size=640, crop_mode=True),
    "base (daha doğru)": dict(base_size=1024, image_size=1024, crop_mode=False),
}

model = tokenizer = None
model_ready = threading.Event()
load_error = []


def load_model():
    global model, tokenizer
    try:
        tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR, trust_remote_code=True)
        model = AutoModel.from_pretrained(
            MODEL_DIR,
            trust_remote_code=True,
            use_safetensors=True,
            torch_dtype=torch.bfloat16,
        ).eval().cuda()
        print("Model ready.", flush=True)
    except Exception as e:  # surfaced to the user in run()
        load_error.append(repr(e))
        raise
    finally:
        model_ready.set()


def pdf_to_images(pdf_path, dpi=200):
    doc = pymupdf.open(pdf_path)
    out_dir = tempfile.mkdtemp(prefix="pdf_")
    mat = pymupdf.Matrix(dpi / 72, dpi / 72)
    paths = []
    for i, page in enumerate(doc):
        path = os.path.join(out_dir, f"page_{i + 1:04d}.png")
        page.get_pixmap(matrix=mat).save(path)
        paths.append(path)
    doc.close()
    return paths


def ocr_image(image_path, mode):
    out_dir = tempfile.mkdtemp(prefix="ocr_")
    model.infer(
        tokenizer,
        prompt="<image>document parsing.",
        image_file=image_path,
        output_path=out_dir,
        max_length=8192,
        no_repeat_ngram_size=35,
        ngram_window=128,
        save_results=True,
        **MODES[mode],
    )
    with open(os.path.join(out_dir, "result.md"), encoding="utf-8") as f:
        return f.read().strip()


def run(file_path, mode, progress=gr.Progress()):
    if not file_path:
        raise gr.Error("Önce bir resim veya PDF yükleyin.")
    if not model_ready.is_set():
        yield "Model yükleniyor, ilk açılışta 1-2 dakika sürebilir...", None
        model_ready.wait()
    if load_error:
        raise gr.Error(f"Model yüklenemedi: {load_error[0]}")

    pages = pdf_to_images(file_path) if file_path.lower().endswith(".pdf") else [file_path]
    parts = []
    for i, page in enumerate(progress.tqdm(pages, desc="Sayfa")):
        text = ocr_image(page, mode)
        parts.append(f"<!-- Sayfa {i + 1} -->\n\n{text}" if len(pages) > 1 else text)
        yield "\n\n---\n\n".join(parts), None

    result = "\n\n---\n\n".join(parts)
    out_path = os.path.join(tempfile.mkdtemp(), "sonuc.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(result)
    yield result, out_path


with gr.Blocks(title="Unlimited-OCR") as demo:
    gr.Markdown("# Unlimited-OCR\nResim veya PDF yükleyin; çıktı Markdown olarak gelir.")
    with gr.Row():
        with gr.Column(scale=1):
            inp = gr.File(label="Belge", file_types=[".pdf", ".png", ".jpg", ".jpeg", ".webp", ".bmp"], type="filepath")
            mode = gr.Radio(list(MODES), value="gundam (hızlı)", label="Mod")
            btn = gr.Button("Çalıştır", variant="primary")
            out_file = gr.File(label="Sonucu indir (.md)")
        with gr.Column(scale=2):
            out_md = gr.Markdown(label="Sonuç")
    btn.click(run, inputs=[inp, mode], outputs=[out_md, out_file])


if __name__ == "__main__":
    threading.Thread(target=load_model, daemon=True).start()
    password = os.environ.get("OCR_PASSWORD")
    demo.queue(default_concurrency_limit=1).launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", 8080)),
        auth=(os.environ.get("OCR_USER", "ocr"), password) if password else None,
        show_api=False,
    )
