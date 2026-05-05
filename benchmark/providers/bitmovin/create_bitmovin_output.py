#!/usr/bin/env python3
"""Create a Bitmovin Generic S3 Output resource pointing to the configured
Hippius bucket, and print the resulting output ID to paste into .env.

Usage:
    python -m benchmark.providers.bitmovin.create_bitmovin_output
"""

import os
import re
import sys

from dotenv import load_dotenv

from bitmovin_api_sdk import BitmovinApi
from bitmovin_api_sdk.models import GenericS3Output

load_dotenv()

REQUIRED_ENV = [
    "BITMOVIN_API_KEY",
    "HIPPIUS_S3_ENDPOINT",
    "HIPPIUS_S3_BUCKET",
    "HIPPIUS_S3_ACCESS_KEY",
    "HIPPIUS_S3_SECRET_KEY",
]


def main():
    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        print(f"ERROR: missing env vars: {', '.join(missing)}")
        sys.exit(1)

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

    print(f"\nSuccess! Add this line to your .env:")
    print(f"\n  BITMOVIN_S3_OUTPUT_ID={output.id}")


if __name__ == "__main__":
    main()
