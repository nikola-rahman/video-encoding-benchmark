#!/usr/bin/env python3
"""Create a Bitmovin Generic S3 Output resource pointing to the configured
Hippius bucket, and print the resulting output ID to paste into .env."""

import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

required = [
    "BITMOVIN_API_KEY",
    "HIPPIUS_S3_ENDPOINT",
    "HIPPIUS_S3_BUCKET",
    "HIPPIUS_S3_ACCESS_KEY",
    "HIPPIUS_S3_SECRET_KEY",
]
missing = [k for k in required if not os.environ.get(k)]
if missing:
    print(f"ERROR: missing env vars: {', '.join(missing)}")
    sys.exit(1)

from bitmovin_api_sdk import BitmovinApi
from bitmovin_api_sdk.models import GenericS3Output

api = BitmovinApi(api_key=os.environ["BITMOVIN_API_KEY"])

host = re.sub(r"^https?://", "", os.environ["HIPPIUS_S3_ENDPOINT"])
bucket = os.environ["HIPPIUS_S3_BUCKET"]

print(f"Creating Bitmovin Generic S3 Output...")
print(f"  Host:   {host}")
print(f"  Bucket: {bucket}")

output = api.encoding.outputs.generic_s3.create(
    generic_s3_output=GenericS3Output(
        name=f"Hippius S3 — {bucket}",
        host=host,
        bucket_name=bucket,
        access_key=os.environ["HIPPIUS_S3_ACCESS_KEY"],
        secret_key=os.environ["HIPPIUS_S3_SECRET_KEY"],
        port=443,
        ssl=True,
    )
)

print(f"\nSuccess! Add this to your .env:\n")
print(f"BITMOVIN_S3_OUTPUT_ID={output.id}")

env_path = Path(".env")
if env_path.exists():
    content = env_path.read_text()
    updated = re.sub(
        r"^BITMOVIN_S3_OUTPUT_ID=.*$",
        f"BITMOVIN_S3_OUTPUT_ID={output.id}",
        content,
        flags=re.MULTILINE,
    )
    if updated != content:
        env_path.write_text(updated)
        print(f"\n.env updated automatically.")
    else:
        print(f"\nCould not auto-update .env — paste the line above manually.")
