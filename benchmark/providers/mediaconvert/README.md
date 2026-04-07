# AWS MediaConvert

Cloud-based video transcoding service from AWS. Uses QVBR (quality-defined variable bitrate) rate control — the encoder targets a perceptual quality level and finds the minimum bitrate to achieve it.

## Status

**Setup verified.** Provider implementation in progress.

## Setup

### 1. Create S3 bucket for outputs

```bash
aws s3 mb s3://<bucket> --region us-east-1
```

### 2. Create IAM role for MediaConvert

```bash
aws iam create-role \
  --role-name MediaConvertBenchmarkRole \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "mediaconvert.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'
```

### 3. Attach S3 permissions to the role

```bash
aws iam put-role-policy \
  --role-name MediaConvertBenchmarkRole \
  --policy-name S3Access \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::<bucket>",
        "arn:aws:s3:::<bucket>/*"
      ]
    }]
  }'
```

### 4. Get the MediaConvert endpoint

```bash
aws mediaconvert describe-endpoints --region us-east-1
```

### 5. Add credentials to .env

```
MEDIACONVERT_ROLE_ARN=arn:aws:iam::ACCOUNT_ID:role/MediaConvertBenchmarkRole
MEDIACONVERT_ENDPOINT=https://mediaconvert.us-east-1.amazonaws.com
MEDIACONVERT_REGION=us-east-1
MEDIACONVERT_S3_OUTPUT_BUCKET=<bucket>
```

AWS credentials (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) are read from `~/.aws/credentials` via `aws configure`.

## Input files

MediaConvert reads inputs via HTTPS URLs. The benchmark generates presigned URLs from Hippius S3 — no need to copy files to AWS S3.

## Encoding settings

QVBR with AWS defaults. The only variable is the quality level (1-10).

- `RateControlMode`: QVBR
- `QvbrQualityLevel`: 1-10 (higher = higher quality)
- `MaxBitrate`: required safety cap (e.g. 6000000 for 1080p)
- All other settings: AWS defaults (auto GOP, adaptive quantization, etc.)

AV1 is also supported but with fewer tuning options (no multi-pass, no scene change detection).

## SDK

```bash
uv add boto3
```

## Key documentation

- **User Guide:** https://docs.aws.amazon.com/mediaconvert/latest/ug/what-is.html
- **Boto3 client:** https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/mediaconvert.html
- **QVBR guidelines:** https://docs.aws.amazon.com/mediaconvert/latest/ug/qvbr-guidelines.html
- **Video quality recommendations:** https://docs.aws.amazon.com/mediaconvert/latest/ug/video-quality.html
- **Pricing:** https://aws.amazon.com/mediaconvert/pricing/
