# Video Compression Benchmark

Multi-provider video encoding benchmark comparing compression efficiency for archival, e-commerce, UGC, and education workloads.

## Setup

```bash
uv sync
cp .env.example .env  # fill in API keys
```

## Project Structure

```
benchmark/              # Encoding pipeline
  providers/            # Provider integrations (one dir each)
    bitmovin/           # Implemented
    mediaconvert/       # Skeleton
    mux/                # Skeleton
    cloudflare/         # Skeleton
    zencoder/           # Skeleton
    manual/             # Filesystem scanner (for Vidaio etc.)
  steps/                # Pipeline steps
  util/                 # FFmpeg, S3, logging helpers
report/                 # Report generation system
  template.md.j2        # Jinja2 report template
  generate.py           # Renders charts + report from CSVs
  charts.py             # All chart generators
  report.yaml           # Config: version, providers, thresholds
  generate_dummy_data.py # Dummy data for testing
data/                   # Runtime data (gitignored except .gitkeep)
  inputs/               # Source video files
  outputs/              # Encoded outputs by provider
research/               # Background research and pilot results
```

## Benchmark Pipeline

```bash
# 1. Place source videos in data/inputs/

# 2. Validate and fix inputs
.venv/bin/python -m benchmark preprocess --fix

# 3. Upload to S3 and generate presigned URLs
.venv/bin/python -m benchmark upload --update-urls

# 4. Submit encoding jobs
.venv/bin/python -m benchmark encode --provider bitmovin --codec av1

# 5. Poll until finished
.venv/bin/python -m benchmark poll --provider bitmovin --watch 30

# 6. Download encoded outputs
.venv/bin/python -m benchmark download --provider bitmovin

# 7. For manual providers (e.g. Vidaio), place files and scan
# Place files in data/outputs/vidaio/<clip>_<codec>_<preset>/output.mp4
.venv/bin/python -m benchmark scan vidaio

# 8. Calculate VMAF scores
.venv/bin/python -m benchmark measure

# 9. Export results to CSVs for report
.venv/bin/python -m benchmark export
```

## Report Generation

```bash
# Generate dummy data for testing
.venv/bin/python report/generate_dummy_data.py

# Generate charts + render report (single command)
.venv/bin/python -m report.generate

# Output: report/output/v{version}_{date}/report.md
# Latest: report/output/latest/report.md
```

To regenerate after new experiment data:
1. Run pipeline steps 1-9 above
2. Run `.venv/bin/python -m report.generate`

Use `--skip-charts` to re-render the report without regenerating charts:
```bash
.venv/bin/python -m report.generate --skip-charts
```

## Provider Setup

Each provider has its own README with credentials, SDK install, and API docs:

- [`benchmark/providers/bitmovin/README.md`](benchmark/providers/bitmovin/README.md)
- [`benchmark/providers/mediaconvert/README.md`](benchmark/providers/mediaconvert/README.md)
- [`benchmark/providers/mux/README.md`](benchmark/providers/mux/README.md)
- [`benchmark/providers/cloudflare/README.md`](benchmark/providers/cloudflare/README.md)
- [`benchmark/providers/zencoder/README.md`](benchmark/providers/zencoder/README.md)
- [`benchmark/providers/manual/README.md`](benchmark/providers/manual/README.md)

## Configuration

- `benchmark.yaml` — pipeline config (providers, codecs, S3 storage)
- `report/report.yaml` — report config (version, thresholds, projections)
- `.env` — API keys and credentials (not committed)

## Available Commands

```
python -m benchmark preprocess   # Validate/fix input videos
python -m benchmark upload       # Upload inputs to S3
python -m benchmark encode       # Submit encoding jobs
python -m benchmark poll         # Check encoding status
python -m benchmark download     # Download encoded outputs
python -m benchmark scan         # Scan manual provider outputs
python -m benchmark measure      # Calculate VMAF scores
python -m benchmark export       # Export results to report CSVs
python -m benchmark report       # Generate basic RD plots
python -m benchmark cleanup      # Clean up remote resources
python -m benchmark run          # Run full pipeline
```
