# AWS MediaConvert

Cloud-based video transcoding service from AWS. Supports QVBR (quality-defined variable bitrate) rate control, which is the closest equivalent to quality-optimized encoding for our benchmark.

## Status

**Not yet implemented.** All methods raise `NotImplementedError`.

## Credentials

| Variable | Description |
|----------|-------------|
| `MEDIACONVERT_ROLE_ARN` | IAM role ARN that MediaConvert assumes to access S3 |
| `MEDIACONVERT_QUEUE_ARN` | (Optional) Job queue ARN. Uses default queue if omitted |
| `MEDIACONVERT_S3_OUTPUT_BUCKET` | S3 bucket for encoded outputs |

The provider uses your default AWS credentials (env vars, `~/.aws/credentials`, or instance profile) via boto3.

## Config (benchmark.yaml)

```yaml
providers:
  mediaconvert:
    enabled: true
    region: us-east-1
    role_arn: ${MEDIACONVERT_ROLE_ARN}
    queue_arn: ${MEDIACONVERT_QUEUE_ARN}
    s3_output_bucket: ${MEDIACONVERT_S3_OUTPUT_BUCKET}
    s3_output_prefix: benchmark-outputs/
```

## SDK

```bash
uv add boto3
```

## Key documentation

- **User Guide:** https://docs.aws.amazon.com/mediaconvert/latest/ug/what-is.html
- **API Reference (Jobs):** https://docs.aws.amazon.com/mediaconvert/latest/apireference/jobs.html
- **Boto3 client reference:** https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/mediaconvert.html
- **Boto3 `create_job()`:** https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/mediaconvert/client/create_job.html
- **Pricing:** https://aws.amazon.com/mediaconvert/pricing/

### Encoding settings

- **QVBR rate control (overview):** https://docs.aws.amazon.com/mediaconvert/latest/ug/cbr-vbr-qvbr.html
- **QVBR guidelines (quality levels per resolution):** https://docs.aws.amazon.com/mediaconvert/latest/ug/qvbr-guidelines.html
- **Video quality recommendations:** https://docs.aws.amazon.com/mediaconvert/latest/ug/video-quality.html
- **Supported codecs & containers:** https://docs.aws.amazon.com/mediaconvert/latest/ug/reference-codecs-containers.html

### Job workflow

- **Setting up a job:** https://docs.aws.amazon.com/mediaconvert/latest/ug/setting-up-a-job.html
- **Example job settings (JSON):** https://docs.aws.amazon.com/mediaconvert/latest/ug/example-job-settings.html
- **Output groups & settings:** https://docs.aws.amazon.com/mediaconvert/latest/ug/output-settings.html

## Notes

- AV1 in MediaConvert only supports QVBR rate control mode (not CBR or VBR).
- The account-specific API endpoint must be discovered at runtime via `describe_endpoints()`.
- Input files should be provided as `s3://` URIs or HTTPS URLs.
