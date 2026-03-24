# Manual Provider

Filesystem-based provider for pre-encoded files. Used for providers where encoding happens outside the benchmark pipeline (e.g., Vidaio encodes are run by their team and the output files are placed locally).

## Status

**Implemented.** Scans `data/outputs/<provider>/` for encoded video files.

## Credentials

None required.

## Config (benchmark.yaml)

Any provider using manual file placement just needs an `enabled` flag:

```yaml
providers:
  vidaio:
    enabled: true
    # Manual provider - no credentials needed
```

## How it works

1. Place encoded files under `data/outputs/<provider_name>/<encoding_name>/`
2. Directory name should start with the input file stem and contain the codec, e.g.:
   - `data/outputs/vidaio/BigBuckBunny_720p_60s_av1_basic/output.mp4`
   - `data/outputs/vidaio/TearsOfSteel_1080p_60s_h265_medium/output.mp4`
3. The provider scans directories, matches to input files, extracts codec from the name, and probes bitrate/size via ffprobe.

## Directory naming convention

```
<input_stem>_<codec>_<variant>/
```

- `input_stem`: Must match a file in `data/inputs/` (e.g., `BigBuckBunny_720p_60s`)
- `codec`: One of `av1`, `h265`, `hevc`, `h264`, `vp9`
- `variant`: Any label (e.g., `basic`, `medium`, `hyper`)

## Notes

- Only one video file per directory is expected. If multiple exist, the largest or one named `output.*` is used.
- Supported extensions: `.mp4`, `.mov`, `.mkv`, `.webm`, `.avi`
