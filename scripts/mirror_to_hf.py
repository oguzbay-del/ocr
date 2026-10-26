"""Copy the Unlimited-OCR model repo (weights + remote code) to our own Hugging Face account.

Usage: HF_TOKEN=<write token> python scripts/mirror_to_hf.py
"""
import os

from huggingface_hub import HfApi, snapshot_download

SOURCE = "baidu/Unlimited-OCR"
TARGET = os.environ.get("HF_TARGET_REPO", "Oguzbayrakdar/Unlimited-OCR")
LOCAL_DIR = os.environ.get("HF_LOCAL_DIR", "hf_mirror")

api = HfApi(token=os.environ["HF_TOKEN"])

revision = api.model_info(SOURCE).sha
print(f"Downloading {SOURCE}@{revision} ...")
snapshot_download(SOURCE, revision=revision, local_dir=LOCAL_DIR)

api.create_repo(TARGET, repo_type="model", private=False, exist_ok=True)
print(f"Uploading to {TARGET} ...")
api.upload_folder(repo_id=TARGET, repo_type="model", folder_path=LOCAL_DIR,
                  ignore_patterns=[".cache/**"],
                  commit_message=f"Mirror {SOURCE}@{revision}")
print(f"Done: https://huggingface.co/{TARGET} (source revision {revision})")
