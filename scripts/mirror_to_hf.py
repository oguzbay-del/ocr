"""Keep our Hugging Face copy of Unlimited-OCR identical to the upstream model repo.

Files are compared by hash and only what changed is transferred, one file at a
time, so the disk of a GitHub Actions runner is enough.

Usage: HF_TOKEN=<write token> python scripts/mirror_to_hf.py [--dry-run]
"""
import argparse
import os
import tempfile

from huggingface_hub import CommitOperationDelete, HfApi, hf_hub_download
from huggingface_hub.hf_api import RepoFile

SOURCE = os.environ.get("HF_SOURCE_REPO", "baidu/Unlimited-OCR")
TARGET = os.environ.get("HF_TARGET_REPO", "Oguzbayrakdar/Unlimited-OCR")


def file_hashes(api, repo, revision=None):
    return {
        f.path: f.lfs.sha256 if f.lfs else f.blob_id
        for f in api.list_repo_tree(repo, revision=revision, recursive=True)
        if isinstance(f, RepoFile)
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="only print what would change")
    args = parser.parse_args()

    api = HfApi(token=os.environ.get("HF_TOKEN"))
    revision = api.model_info(SOURCE).sha
    source = file_hashes(api, SOURCE, revision)

    if api.repo_exists(TARGET):
        target = file_hashes(api, TARGET)
    else:
        target = {}
        if not args.dry_run:
            api.create_repo(TARGET, repo_type="model", private=False)

    changed = sorted(p for p, h in source.items() if target.get(p) != h)
    removed = sorted(p for p in target if p not in source)
    print(f"{SOURCE}@{revision}: {len(changed)} changed, {len(removed)} removed")
    for p in changed:
        print(f"  update {p}")
    for p in removed:
        print(f"  delete {p}")
    if args.dry_run or not (changed or removed):
        return

    for path in changed:
        with tempfile.TemporaryDirectory() as tmp:
            local = hf_hub_download(SOURCE, path, revision=revision, local_dir=tmp)
            api.upload_file(
                path_or_fileobj=local,
                path_in_repo=path,
                repo_id=TARGET,
                commit_message=f"Sync {path} from {SOURCE}@{revision[:7]}",
            )
    if removed:
        api.create_commit(
            repo_id=TARGET,
            operations=[CommitOperationDelete(path_in_repo=p) for p in removed],
            commit_message=f"Remove files deleted in {SOURCE}@{revision[:7]}",
        )
    print(f"Done: https://huggingface.co/{TARGET}")


if __name__ == "__main__":
    main()
