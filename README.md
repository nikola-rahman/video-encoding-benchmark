# Video Compression Benchmark

Multi-provider video encoding benchmark comparing compression efficiency for archival, e-commerce, UGC, security, and education workloads.

## Setup

```bash
uv sync
cp .env.example .env  # fill in API keys
```

Requires `ffmpeg` and `yt-dlp` installed on your system:
```bash
brew install ffmpeg yt-dlp
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
  samples/              # Video sample management
    catalog.yaml        # What videos to use and where to get them
    download.py         # Download raw samples from URLs
    prepare.py          # Re-encode to H.264 CRF 18 benchmark inputs
  steps/                # Pipeline steps
  util/                 # FFmpeg, S3, logging helpers
report/                 # Report generation system
  template.md.j2        # Jinja2 report template
  generate.py           # Renders charts + report from CSVs
  charts.py             # All chart generators
  report.yaml           # Config: version, providers, thresholds
data/                   # Runtime data (gitignored except .gitkeep)
  samples/
    raw/                # Layer 1: downloaded originals (any format, any duration)
    prepared/           # Layer 2: re-encoded H.264 CRF 18, trimmed, benchmark-ready
  outputs/              # Layer 3: encoded files by provider
  results/              # Layer 4: VMAF scores, metadata
research/               # Background research and pilot results
```

## Full Workflow

### 1. Get video samples

Download prepared samples from S3 (the default path):

```bash
# Download prepared benchmark inputs from S3
.venv/bin/python -m benchmark.samples.download data/samples/prepared samples/prepared

# Download raw originals from S3
.venv/bin/python -m benchmark.samples.download data/samples/raw samples/raw
```

To build samples from scratch (first time setup or adding new videos):

```bash
# Download from original sources (YouTube, archive.org, etc.)
.venv/bin/python -m benchmark.samples.source data/samples/raw

# For manual sources (e.g. VIRAT), place files in data/samples/raw/{id}.mp4
```

### 2. Prepare benchmark inputs

Re-encodes all raw samples to H.264 CRF 18, no audio, MP4. Videos longer than `max_duration` (default 120s) are automatically trimmed. Per-source `trim` settings in `catalog.yaml` override the default.

```bash
.venv/bin/python -m benchmark.samples.prepare data/samples/raw data/samples/prepared
```

### 3. Upload to S3

```bash
# Upload prepared inputs
.venv/bin/python -m benchmark.samples.upload data/samples/prepared samples/prepared

# Upload raw originals
.venv/bin/python -m benchmark.samples.upload data/samples/raw samples/raw
```

### 4. Encode with providers

```bash
# Cloud providers (submit job)
.venv/bin/python -m benchmark encode --provider bitmovin --codec av1

# Poll until finished
.venv/bin/python -m benchmark poll --provider bitmovin --watch 30

# Download encoded outputs
.venv/bin/python -m benchmark download --provider bitmovin

# Manual providers (e.g. Vidaio) — place files and scan
# Place in data/outputs/vidaio/<clip>_<codec>_<preset>/output.mp4
.venv/bin/python -m benchmark scan vidaio
```

### 5. Measure quality

```bash
.venv/bin/python -m benchmark measure
```

### 6. Export and generate report

```bash
# Export pipeline results to CSVs
.venv/bin/python -m benchmark export

# Generate charts + render report
.venv/bin/python -m report.generate

# Output: report/output/latest/report.md
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
- `benchmark/samples/catalog.yaml` — video sample sources and trim settings
- `report/report.yaml` — report config (version, thresholds, projections)
- `.env` — API keys and credentials (not committed)

## CLI Commands

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

## Standalone Scripts

```
python -m benchmark.samples.download <local_dir> <s3_prefix>       # Download from S3
python -m benchmark.samples.upload <local_dir> <s3_prefix>         # Upload to S3
python -m benchmark.samples.source <output_dir>                    # Download from original sources
python -m benchmark.samples.prepare <raw_dir> <output_dir>         # Prepare benchmark inputs
python -m report.generate                                          # Generate charts + render report
```
