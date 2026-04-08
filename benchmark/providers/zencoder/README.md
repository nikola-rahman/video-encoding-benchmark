# Brightcove Zencoder

Cloud transcoding API from Brightcove. Supports H.265/HEVC and AV1 with quality (1-5) and CRF (0-51) controls.

## Status

**Setup verified.** Provider implementation in progress.

## Setup

### 1. Create account

Sign up at https://app.zencoder.com/signup (includes free integration/test mode).

### 2. Grant Zencoder access to AWS S3 output bucket

Zencoder writes outputs to AWS S3. Add a bucket policy granting Zencoder's AWS account access:

```bash
aws s3api put-bucket-policy --bucket <bucket> --region us-east-1 --policy '{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ZencoderAccess",
      "Effect": "Allow",
      "Principal": {"AWS": "arn:aws:iam::<account-id>:root"},
      "Action": [
        "s3:GetObject",
        "s3:GetObjectAcl",
        "s3:PutObject",
        "s3:PutObjectAcl",
        "s3:ListMultipartUploadParts",
        "s3:ListBucketMultipartUploads",
        "s3:GetBucketLocation"
      ],
      "Resource": [
        "arn:aws:s3:::<bucket>",
        "arn:aws:s3:::<bucket>/*"
      ]
    }
  ]
}'
```

### 3. Add credentials to .env

```
ZENCODER_API_KEY=your_full_access_api_key
```

## Input files

Zencoder reads inputs via HTTPS URLs. The benchmark generates presigned URLs from Hippius S3 via `prepare_input()`.

## Output files

Zencoder writes to AWS S3 bucket `<bucket>`. Use `s3+us-east-1://bucket/prefix/` format for the output URL.

## Encoding settings

Quality parameter (1-5) with best speed (1 = slowest/best).

- `video_codec`: `hevc` for H.265, `av1` for AV1
- `quality`: 1 (lowest) to 5 (highest)
- `speed`: 1 (slowest/best) to 5 (fastest) — we use 1 for best compression

## Key documentation

- **API Reference:** https://zencoder.support.brightcove.com/references/reference.html
- **Legacy API docs:** https://app.zencoder.com/docs/api
- **Pricing:** https://zencoder.com/en/file-transcoding/pricing
- **Quality settings:** https://app.zencoder.com/docs/api/encoding/rate-control/quality
