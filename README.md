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
  samples/raw/          # Downloaded raw videos (any format)
  inputs/               # Prepared benchmark inputs (H.264 CRF 18)
  outputs/              # Encoded outputs by provider
research/               # Background research and pilot results
```

## Full Workflow

### 1. Get video samples

Edit `benchmark/samples/catalog.yaml` to define source videos. Each entry has an id, vertical, URL, and download method (ffmpeg, yt-dlp, http, or manual). Videos longer than `max_duration` (default 120s) are automatically trimmed from the start. Per-source `trim` settings override the default.

```bash
# Download all raw samples
.venv/bin/python -m benchmark.samples.download

# Download one vertical
.venv/bin/python -m benchmark.samples.download --vertical ecommerce

# For manual sources (e.g. VIRAT), place files in data/samples/raw/{id}.mp4
```

### 2. Prepare benchmark inputs

Re-encodes all raw samples to H.264 CRF 18, no audio, MP4. Trims to duration specified in catalog.

```bash
.venv/bin/python -m benchmark.samples.prepare

# Prepare one vertical
.venv/bin/python -m benchmark.samples.prepare --vertical security

# Re-encode even if output exists
.venv/bin/python -m benchmark.samples.prepare --force
```

Output goes to `data/inputs/`.

### 3. Validate inputs

```bash
.venv/bin/python -m benchmark preprocess --fix
```

### 4. Upload to S3

```bash
.venv/bin/python -m benchmark upload --update-urls
```

### 5. Encode with providers

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

### 6. Measure quality

```bash
.venv/bin/python -m benchmark measure
```

### 7. Export and generate report

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
python -m benchmark.samples.download   # Download raw video samples
python -m benchmark.samples.prepare    # Prepare benchmark inputs (H.264 CRF 18)
python -m report.generate              # Generate charts + render report
```
