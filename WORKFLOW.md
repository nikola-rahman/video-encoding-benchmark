# Video Compression Benchmark Workflow

Step-by-step guide to benchmarking video compression quality across providers.

## Prerequisites

### Linux (Ubuntu / Debian) — recommended

```bash
sudo apt-get update && sudo apt-get install -y git curl

# uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

# ffmpeg 7.1 (with libvmaf, libx265, libsvtav1)
cd /tmp
curl -L -o ffmpeg-n7.1.tar.xz https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n7.1-latest-linux64-gpl-7.1.tar.xz
tar -xf ffmpeg-n7.1.tar.xz
sudo mv ffmpeg-n7.1-latest-linux64-gpl-7.1 /usr/local/lib/ffmpeg-7.1
sudo ln -sf /usr/local/lib/ffmpeg-7.1/bin/ffmpeg /usr/local/bin/ffmpeg
sudo ln -sf /usr/local/lib/ffmpeg-7.1/bin/ffprobe /usr/local/bin/ffprobe

# repo
git clone git@github.com:nikola-rahman/video-compression-benchmark.git
cd video-compression-benchmark
uv sync
```

### macOS

```bash
brew install ffmpeg uv git
uv sync
```

Configure `.env`:
```
BITMOVIN_API_KEY=...
BITMOVIN_S3_OUTPUT_ID=...
HIPPIUS_S3_ENDPOINT=https://s3.hippius.com
HIPPIUS_S3_BUCKET=<bucket>
HIPPIUS_S3_ACCESS_KEY=...
HIPPIUS_S3_SECRET_KEY=...
HIPPIUS_S3_REGION=decentralized
```

Provider settings and pipeline config are in `benchmark.yaml`. Credentials stay in `.env` and are referenced via `${ENV_VAR}` interpolation.

## Step 1: Prepare Input Videos

Place source videos in `data/inputs/`. These are the reference files that all providers encode and all VMAF scores are measured against.

```bash
python -m benchmark preprocess          # check only
python -m benchmark preprocess --fix    # fix any issues found
```

What it fixes:
- **B-frame flush**: h264 files trimmed with `-c copy` can decode to more frames than the container reports, causing VMAF pipe errors. Fix: re-encode lossless with no B-frames.
- **Audio tracks**: stripped (not needed for video quality benchmarks).
- **Fractional duration**: trimmed to clean integer second boundary.

## Step 2: Upload Inputs to S3

Bitmovin requires HTTPS-accessible input files. Upload to Hippius S3 and generate presigned URLs:

```bash
python -m benchmark upload --update-urls
```

This uploads all files in `data/inputs/` to `s3://<bucket>/benchmark-inputs/` and writes presigned URLs to `video_urls.txt`.

## Step 3: Submit Encodings

```bash
python -m benchmark encode --codec av1                      # AV1 only
python -m benchmark encode --codec h265                     # H.265 only
python -m benchmark encode                                  # all codecs, all providers
python -m benchmark encode --provider bitmovin --codec av1  # specific provider
```

Uses Per-Title encoding with progressive MP4 output. Bitmovin automatically generates a bitrate ladder based on content complexity.

Monitor progress:
```bash
python -m benchmark poll               # check once
python -m benchmark poll --watch 30    # poll every 30 seconds
```

## Step 4: Download Results

```bash
python -m benchmark download                         # all completed
python -m benchmark download --encoding-id <ID>      # specific encoding
python -m benchmark download --list                  # list only
```

Downloads encoded outputs from S3 to `data/outputs/bitmovin/` and writes `data/metadata.json`.

## Step 5: Add Other Provider Outputs

### Directory structure

Place encoded files under `data/outputs/<provider>/<encoding_name>/`:

```
data/outputs/
  vidaio/
    BigBuckBunny_720p_60s_av1_basic/
      <uuid>_final.mp4
    BigBuckBunny_720p_60s_av1_hyper/
      <uuid>_final.mp4
    TearsOfSteel_1080p_60s_av1_medium/
      output.mp4
```

Naming convention: `<input_stem>_<codec>[_<variant>]`
- The input stem (e.g. `BigBuckBunny_720p_60s`) is used to match against files in `data/inputs/`
- Codec must appear in the directory name (`av1`, `h265`, `h264`, `vp9`)
- Variant suffix is optional (e.g. `basic`, `medium`, `hyper`, `crf23`)

### Register outputs

```bash
python -m benchmark scan vidaio   # scan all dirs under data/outputs/vidaio/
```

This appends entries to `data/metadata.json` with bitrate info extracted via ffprobe.

## Step 6: Calculate VMAF

```bash
python -m benchmark measure                          # full video VMAF
python -m benchmark measure --seed 42 --duration 10  # 10-second sample
python -m benchmark measure --threads 8              # more threads
```

Results are written to `data/vmaf_results.json` and printed as a summary table.

## Step 7: Generate Reports

```bash
python -m benchmark report
```

Generates rate-distortion plots and summary tables from VMAF results.

## Cleanup

To start fresh or re-run Bitmovin encodings:

```bash
python -m benchmark cleanup                          # dry run: list what would be deleted
python -m benchmark cleanup --delete                 # delete Bitmovin jobs + S3 files + local files
python -m benchmark cleanup --delete --keep-local    # delete remote only
```

## Full Example: Bitmovin vs Vidaio

```bash
# 1. Prepare inputs
python -m benchmark preprocess --fix

# 2. Upload to S3
python -m benchmark upload --update-urls

# 3. Submit Bitmovin encodings
python -m benchmark encode --provider bitmovin --codec av1
python -m benchmark poll --watch 30          # wait for completion

# 4. Download Bitmovin results
python -m benchmark download

# 5. Add Vidaio outputs (already placed in data/outputs/vidaio/)
python -m benchmark scan vidaio

# 6. Run VMAF
python -m benchmark measure

# 7. Generate plots
python -m benchmark report
```

Or run the full pipeline:
```bash
python -m benchmark run --provider bitmovin
python -m benchmark run --skip poll   # skip polling step
```

## Adding a New Provider

1. Create `benchmark/providers/newprovider.py` with a class inheriting from `Provider`
2. Add one import + one line in `benchmark/providers/__init__.py`
3. Add config section in `benchmark.yaml`

## Architecture

```
benchmark/
  __main__.py        CLI entry point (python -m benchmark <command>)
  config.py          YAML loader with ${ENV_VAR} interpolation
  metadata.py        metadata.json + vmaf_results.json read/write
  util/
    ffmpeg.py        ffprobe/ffmpeg/vmaf wrappers
    s3.py            S3 client + upload/download/presign/delete
    log.py           Shared logging setup
  providers/
    __init__.py      Provider registry
    base.py          Provider ABC + EncodingResult/Rendition dataclasses
    bitmovin.py      Bitmovin cloud API
    manual.py        Manual file placement
  steps/
    preprocess.py    Validate/fix inputs
    upload.py        Upload inputs to S3
    encode.py        Dispatch to provider.submit()
    poll.py          Dispatch to provider.check_status()
    download.py      Dispatch to provider.download()
    measure.py       VMAF calculation (provider-agnostic)
    report.py        Rate-distortion plots + summary tables
    cleanup.py       Dispatch to provider.cleanup()
```

| Data File | Purpose |
|-----------|---------|
| `.env` | API keys and S3 credentials |
| `benchmark.yaml` | Pipeline config with `${ENV_VAR}` interpolation |
| `video_urls.txt` | Presigned input URLs for Bitmovin |
| `data/metadata.json` | All encodings across all providers |
| `data/vmaf_results.json` | VMAF scores for all renditions |
