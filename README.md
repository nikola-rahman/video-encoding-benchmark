# Video Compression Benchmark

Multi-provider video encoding benchmark comparing compression efficiency for archival, e-commerce, UGC, security, and education workloads.

## Setup

```bash
uv sync
cp .env.example .env  # fill in API keys
```

## Project Structure

```
benchmark/              # Encoding pipeline
  providers/            # Provider integrations (one dir each)
    base.py             # Provider ABC + quality binary search
    bitmovin/           # Implemented
    mediaconvert/       # In progress
    mux/                # Skeleton
    cloudflare/         # Skeleton
    zencoder/           # Skeleton
    manual/             # Filesystem scanner (for Vidaio etc.)
  samples/              # Video sample management
    catalog.yaml        # What videos to use and where to get them
    source.py           # Download from original sources
    download.py         # Download from S3
    upload.py           # Upload to S3
    prepare.py          # Re-encode raw → H.264 CRF 18
  steps/                # Pipeline steps
  util/                 # FFmpeg, S3, logging helpers
report/                 # Report generation system
  template.md.j2        # Jinja2 report template
  generate.py           # Renders charts + report from CSVs
  charts.py             # All chart generators
  report.yaml           # Config: version, providers, thresholds
data/                   # Runtime data (gitignored except .gitkeep)
  samples/
    raw/                # Layer 1: downloaded originals (any format)
    prepared/           # Layer 2: H.264 CRF 18, trimmed, benchmark-ready
  outputs/              # Layer 3: encoded files by provider
  results/              # Layer 4: VMAF scores, metadata
research/               # Background research and pilot results
```

## Full Workflow

### 1. Get video samples

Download prepared samples from S3 (the default path):

```bash
.venv/bin/python -m benchmark.samples.download data/samples/prepared samples/prepared
```

To build samples from scratch (first time or adding new videos):

```bash
# Download from original sources (YouTube, archive.org, etc.)
.venv/bin/python -m benchmark.samples.source data/samples/raw

# Prepare (re-encode to H.264 CRF 18, trim long videos)
.venv/bin/python -m benchmark.samples.prepare data/samples/raw data/samples/prepared

# Upload to S3 for sharing
.venv/bin/python -m benchmark.samples.upload data/samples/prepared samples/prepared
```

### 2. Encode with providers

Each provider handles its own input preparation (presigning, S3 access, etc.) internally.

```bash
# Cloud providers (submit job)
.venv/bin/python -m benchmark encode --provider mediaconvert --codec h265

# Poll until finished
.venv/bin/python -m benchmark poll --provider mediaconvert

# Download encoded outputs
.venv/bin/python -m benchmark download --provider mediaconvert

# Manual providers (e.g. Vidaio) — place files and scan
.venv/bin/python -m benchmark scan vidaio
```

### 3. Measure quality

```bash
.venv/bin/python -m benchmark measure
```

### 4. Export and generate report

```bash
.venv/bin/python -m benchmark export
.venv/bin/python -m report.generate
# Output: report/output/latest/report.md
```

## Adding a New Provider

Each provider is a Python package under `benchmark/providers/` with:

```
benchmark/providers/myprovider/
  __init__.py           # Re-exports the provider class
  provider.py           # Provider implementation
  README.md             # Setup, credentials, API docs
```

A provider must extend `benchmark.providers.base.Provider` and implement:

| Method | Required | Description |
|--------|----------|-------------|
| `prepare_input(input_file, s3_key)` | Yes | Return a URL/path the provider can use to access the input. Bitmovin presigns a Hippius URL. MediaConvert presigns a Hippius URL. A local provider returns the file path. |
| `get_results(input_file, codec)` | Yes | Submit an encoding job. Return `EncodingResult` with `encoding_id`. |
| `check_status(encoding_id)` | If cloud | Poll job status. Return dict with `status`, `progress`. |
| `download(result, output_dir)` | If cloud | Download encoded output. Return `EncodingResult` with `renditions` populated. |
| `cleanup(result)` | Optional | Delete remote resources (S3 outputs, jobs). |
| `encode_to_target_vmaf(input_file, codec, target_vmaf, measure_vmaf)` | Yes | Encode to hit a target VMAF. Use `_search_continuous()` for float params (CRF, QVBR), `_search_discrete()` for finite sets (quality 1-5). Providers with native VMAF targeting (e.g. Vidaio) override entirely. |
| `encode_at_quality(input_file, codec, quality)` | Yes | Encode at a specific quality level. Return `EncodingResult` with local file ready for VMAF. |

Register the provider in `benchmark/providers/__init__.py`:

```python
PROVIDERS = {
    ...
    "myprovider": MyProvider,
}
```

Add non-secret settings to `benchmark.yaml`:

```yaml
providers:
  myprovider:
    enabled: true
    some_setting: value
```

Credentials go in `.env`:

```
MYPROVIDER_API_KEY=...
```

## Provider Setup

Each provider has its own README with setup steps and API docs:

- [`benchmark/providers/bitmovin/README.md`](benchmark/providers/bitmovin/README.md)
- [`benchmark/providers/mediaconvert/README.md`](benchmark/providers/mediaconvert/README.md)
- [`benchmark/providers/mux/README.md`](benchmark/providers/mux/README.md)
- [`benchmark/providers/cloudflare/README.md`](benchmark/providers/cloudflare/README.md)
- [`benchmark/providers/zencoder/README.md`](benchmark/providers/zencoder/README.md)
- [`benchmark/providers/manual/README.md`](benchmark/providers/manual/README.md)

## Configuration

- `benchmark.yaml` — pipeline settings (providers, codecs, paths)
- `benchmark/samples/catalog.yaml` — video sample sources and trim settings
- `report/report.yaml` — report config (version, thresholds, projections)
- `.env` — all credentials (not committed)

## Standalone Scripts

```
python -m benchmark.samples.download <local_dir> <s3_prefix>       # Download from S3
python -m benchmark.samples.upload <local_dir> <s3_prefix>         # Upload to S3
python -m benchmark.samples.source <output_dir>                    # Download from original sources
python -m benchmark.samples.prepare <raw_dir> <output_dir>         # Prepare benchmark inputs
python -m report.generate                                          # Generate charts + render report
```
