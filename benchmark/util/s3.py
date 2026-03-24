"""S3 client and operations consolidated from existing scripts."""

import sys
from pathlib import Path

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from benchmark.util.log import setup_logging

log = setup_logging("s3")


def get_s3_client(config: dict):
    """Create an S3 client from the storage.s3 config section."""
    s3_cfg = config["storage"]["s3"]
    access_key = s3_cfg.get("access_key", "")
    secret_key = s3_cfg.get("secret_key", "")

    if not access_key or not secret_key:
        log.error("S3 access_key / secret_key not configured")
        sys.exit(1)

    return boto3.client(
        "s3",
        endpoint_url=s3_cfg["endpoint"],
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=s3_cfg.get("region", "us-east-1"),
        config=BotoConfig(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
    )


def object_exists(s3_client, bucket: str, key: str) -> bool:
    """Check if an object already exists in S3."""
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return False
        raise


def upload_file(s3_client, local_path: Path, bucket: str, key: str, skip_existing: bool = True) -> bool:
    """Upload a file to S3. Returns True if uploaded, False if skipped."""
    if skip_existing and object_exists(s3_client, bucket, key):
        log.info(f"  Already exists in S3: {key}")
        return False

    file_size = local_path.stat().st_size
    log.info(f"  Uploading: {local_path.name} ({file_size / (1024 * 1024):.1f} MB) -> s3://{bucket}/{key}")
    s3_client.upload_file(str(local_path), bucket, key)
    log.info(f"  Uploaded successfully")
    return True


def download_prefix(s3_client, bucket: str, prefix: str, local_dir: Path) -> list[dict]:
    """Download all files under an S3 prefix to a local directory. Returns list of downloaded files."""
    downloaded = []
    paginator = s3_client.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            rel_path = key[len(prefix):].lstrip("/")
            if not rel_path:
                continue

            local_path = local_dir / rel_path
            local_path.parent.mkdir(parents=True, exist_ok=True)

            if local_path.exists() and local_path.stat().st_size == obj["Size"]:
                log.info(f"    Already downloaded: {rel_path}")
            else:
                log.info(f"    Downloading: {rel_path} ({obj['Size'] / 1024:.1f} KB)")
                s3_client.download_file(bucket, key, str(local_path))

            downloaded.append({
                "s3_key": key,
                "local_path": str(local_path),
                "size_bytes": obj["Size"],
            })

    return downloaded


def delete_prefix(s3_client, bucket: str, prefix: str) -> int:
    """Delete all objects under an S3 prefix. Returns count of deleted objects."""
    deleted = 0
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        objects = page.get("Contents", [])
        if not objects:
            continue
        delete_keys = [{"Key": obj["Key"]} for obj in objects]
        s3_client.delete_objects(Bucket=bucket, Delete={"Objects": delete_keys})
        deleted += len(delete_keys)
    return deleted


def presign_url(s3_client, bucket: str, key: str, expires_in: int) -> str:
    """Generate a presigned GET URL."""
    return s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_in,
    )
