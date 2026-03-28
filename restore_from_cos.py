#!/usr/bin/env python3
"""Restore ClawDramas data from COS bucket to local (or to a server via rsync).

Usage:
    python3 restore_from_cos.py              # download to local data/ and static/images/
    python3 restore_from_cos.py --push HOST  # also rsync to HOST after downloading
"""
import json
import os
import sys
from pathlib import Path

from qcloud_cos import CosConfig, CosS3Client

# Config
CREDS_PATH = os.path.expanduser("~/.tccli/default.credential")
creds = json.load(open(CREDS_PATH))

BUCKET = "openclaw-backup-1301327510"
REGION = "eu-frankfurt"
LOCAL_DIR = Path(__file__).parent

config = CosConfig(Region=REGION, SecretId=creds["secretId"], SecretKey=creds["secretKey"])
client = CosS3Client(config)


def list_objects(prefix):
    """List all objects with given prefix."""
    objects = []
    marker = ""
    while True:
        resp = client.list_objects(Bucket=BUCKET, Prefix=prefix, Marker=marker, MaxKeys=1000)
        for obj in resp.get("Contents", []):
            objects.append(obj["Key"])
        if resp.get("IsTruncated") == "false":
            break
        marker = resp.get("NextMarker", "")
    return objects


def download():
    dramas_dir = LOCAL_DIR / "data" / "dramas"
    images_dir = LOCAL_DIR / "static" / "images"
    dramas_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    # Download dramas
    drama_keys = list_objects("dramas/")
    for key in drama_keys:
        filename = key.split("/")[-1]
        if not filename:
            continue
        local_path = str(dramas_dir / filename)
        client.download_file(Bucket=BUCKET, Key=key, DestFilePath=local_path)
        print(f"  {key} -> {local_path}")

    # Download images
    image_keys = list_objects("images/")
    for key in image_keys:
        filename = key.split("/")[-1]
        if not filename:
            continue
        local_path = str(images_dir / filename)
        client.download_file(Bucket=BUCKET, Key=key, DestFilePath=local_path)
        print(f"  {key} -> {local_path}")

    print(f"\nDownloaded {len(drama_keys)} dramas, {len(image_keys)} images")
    return len(drama_keys), len(image_keys)


if __name__ == "__main__":
    print("Downloading from COS...")
    download()

    if "--push" in sys.argv:
        idx = sys.argv.index("--push")
        host = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "ubuntu@43.157.18.154"
        print(f"\nPushing to {host}...")
        os.system(f'rsync -avz -e "ssh -o StrictHostKeyChecking=no" {LOCAL_DIR}/data/dramas/ {host}:~/moltbot/data/dramas/')
        os.system(f'rsync -avz -e "ssh -o StrictHostKeyChecking=no" {LOCAL_DIR}/static/images/ {host}:~/moltbot/static/images/')
        print("Done!")
