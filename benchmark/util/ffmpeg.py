"""FFmpeg/ffprobe/VMAF wrappers consolidated from existing scripts."""

import json
import os
import glob as glob_mod
import random
import shutil
import subprocess
import tempfile
from pathlib import Path

from benchmark.util.log import setup_logging

log = setup_logging("ffmpeg")


def get_stream_info(path: str | Path) -> dict:
    """Get video stream info via ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=nb_frames,duration,codec_name,width,height,r_frame_rate,pix_fmt",
            "-of", "json",
            str(path),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    if not streams:
        raise RuntimeError(f"No video stream found in {path}")
    return streams[0]


def get_video_info(path: str | Path) -> dict:
    """Get bitrate, duration, resolution via ffprobe (format + stream info)."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration,bit_rate:stream=width,height,codec_name",
            "-of", "json",
            str(path),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    return json.loads(result.stdout)


def get_video_duration(path: str | Path) -> float:
    """Get video duration in seconds using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {result.stderr}")
    return float(result.stdout.strip())


def get_actual_bitrate(path: str | Path) -> int | None:
    """Get actual video bitrate from file via ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=bit_rate", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip().isdigit():
        return int(result.stdout.strip())
    return None


def has_audio(path: str | Path) -> bool:
    """Check if file has audio streams."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=index",
            "-of", "csv=p=0",
            str(path),
        ],
        capture_output=True, text=True,
    )
    return bool(result.stdout.strip())


def count_decoded_frames(path: str | Path, width: int, height: int) -> int:
    """Count actual decoded frames by decoding to raw video."""
    frame_bytes = width * height * 3 // 2  # yuv420p
    result = subprocess.run(
        [
            "ffmpeg", "-v", "error",
            "-i", str(path),
            "-pix_fmt", "yuv420p",
            "-f", "rawvideo", "-c:v", "rawvideo", "-",
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg decode failed: {result.stderr.decode()}")
    total_bytes = len(result.stdout)
    return total_bytes // frame_bytes


def check_video(path: str | Path) -> tuple[list[dict], dict]:
    """Check a video file for common issues. Returns (issues, stream_info)."""
    path = str(path)
    issues = []

    info = get_stream_info(path)
    width = int(info["width"])
    height = int(info["height"])
    container_frames = int(info.get("nb_frames", 0))
    codec = info.get("codec_name", "unknown")
    duration = float(info.get("duration", 0))

    log.info(f"  Codec: {codec}, {width}x{height}, {container_frames} frames, {duration:.3f}s")

    if has_audio(path):
        issues.append({
            "type": "audio",
            "message": "Contains audio tracks (unnecessary for video quality benchmark)",
        })

    decoded_frames = count_decoded_frames(path, width, height)
    if decoded_frames != container_frames:
        issues.append({
            "type": "frame_mismatch",
            "message": f"Decoded {decoded_frames} frames but container says {container_frames} "
                       f"(likely B-frame flush from mid-GOP trim)",
            "decoded": decoded_frames,
            "container": container_frames,
        })
    else:
        log.info(f"  Frame count OK: {decoded_frames} decoded == {container_frames} in container")

    frac = duration % 1.0
    if frac > 0.001 and frac < 0.999:
        issues.append({
            "type": "fractional_duration",
            "message": f"Duration {duration:.6f}s is not a clean integer second boundary",
        })

    return issues, info


def fix_video(path: str | Path, issues: list[dict]) -> None:
    """Fix issues by re-encoding with lossless h264, no B-frames, no audio."""
    path = Path(path)
    tmp_path = path.with_suffix(".tmp.mp4")

    info = get_stream_info(str(path))
    duration = float(info.get("duration", 0))
    target_duration = int(duration)

    log.info(f"  Re-encoding: lossless h264, no B-frames, no audio, {target_duration}s")
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(path),
            "-t", str(target_duration),
            "-c:v", "libx264", "-qp", "0", "-bf", "0",
            "-an",
            str(tmp_path),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError(f"Re-encode failed: {result.stderr}")

    shutil.move(str(tmp_path), str(path))
    log.info(f"  Fixed: {path.name} ({path.stat().st_size / (1024 * 1024):.1f} MB)")


def remux_fmp4_to_mp4(rendition_dir: str | Path) -> str:
    """Concatenate init.mp4 + segment_*.m4s and remux to a clean MP4.
    Returns path to the remuxed file."""
    rendition_dir = Path(rendition_dir)
    output_mp4 = rendition_dir / "rendition.mp4"

    if output_mp4.exists():
        log.info(f"    Remuxed MP4 already exists: {output_mp4.name}")
        return str(output_mp4)

    init_file = rendition_dir / "init.mp4"
    segment_files = sorted(glob_mod.glob(str(rendition_dir / "segment_*.m4s")))

    if not init_file.exists():
        raise FileNotFoundError(f"Missing init.mp4 in {rendition_dir}")
    if not segment_files:
        raise FileNotFoundError(f"No segment_*.m4s files in {rendition_dir}")

    concat_tmp = rendition_dir / "concat_tmp.fmp4"
    try:
        with open(concat_tmp, "wb") as out:
            with open(init_file, "rb") as f:
                out.write(f.read())
            for seg in segment_files:
                with open(seg, "rb") as f:
                    out.write(f.read())

        result = subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error",
                "-i", str(concat_tmp),
                "-c", "copy",
                str(output_mp4),
            ],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg remux failed: {result.stderr}")

        log.info(f"    Remuxed: {output_mp4.name} ({output_mp4.stat().st_size / 1024:.1f} KB)")
    finally:
        if concat_tmp.exists():
            concat_tmp.unlink()

    return str(output_mp4)


def compute_start_time(video_duration: float, sample_duration: float, seed: int) -> float:
    """Pick a deterministic random start time for sampling."""
    max_start = video_duration - sample_duration
    if max_start <= 0:
        return 0.0
    rng = random.Random(seed)
    return round(rng.uniform(0, max_start), 3)


def run_vmaf(
    reference_mp4: str | Path,
    distorted_mp4: str | Path,
    output_json: str | Path,
    start_time: float | None = None,
    duration: float | None = None,
    threads: int | None = None,
    model: str | None = None,
) -> dict:
    """Run VMAF comparison using named pipes for y4m conversion.
    Returns parsed VMAF JSON result."""
    reference_mp4 = str(reference_mp4)
    distorted_mp4 = str(distorted_mp4)
    output_json = str(output_json)

    with tempfile.TemporaryDirectory() as tmpdir:
        ref_fifo = os.path.join(tmpdir, "ref.y4m")
        dist_fifo = os.path.join(tmpdir, "dist.y4m")
        os.mkfifo(ref_fifo)
        os.mkfifo(dist_fifo)

        def build_ffmpeg_cmd(input_path, fifo_path):
            cmd = ["ffmpeg", "-v", "error", "-i", input_path]
            if start_time is not None:
                cmd += ["-ss", str(start_time)]
            if duration is not None:
                cmd += ["-t", str(duration)]
            cmd += ["-pix_fmt", "yuv420p", "-f", "yuv4mpegpipe", "-y", fifo_path]
            return cmd

        ref_cmd = build_ffmpeg_cmd(reference_mp4, ref_fifo)
        dist_cmd = build_ffmpeg_cmd(distorted_mp4, dist_fifo)

        vmaf_cmd = [
            "vmaf",
            "-r", ref_fifo,
            "-d", dist_fifo,
            "--json",
            "-o", output_json,
            "-q",
        ]
        if threads is not None:
            vmaf_cmd += ["--threads", str(threads)]
        if model:
            vmaf_cmd += ["-m", model]

        ref_proc = subprocess.Popen(ref_cmd, stderr=subprocess.PIPE)
        dist_proc = subprocess.Popen(dist_cmd, stderr=subprocess.PIPE)
        vmaf_result = subprocess.run(vmaf_cmd, capture_output=True, text=True)

        ref_proc.wait()
        dist_proc.wait()

        if ref_proc.returncode != 0:
            stderr = ref_proc.stderr.read().decode() if ref_proc.stderr else ""
            raise RuntimeError(f"ffmpeg (reference) failed: {stderr}")
        if dist_proc.returncode != 0:
            stderr = dist_proc.stderr.read().decode() if dist_proc.stderr else ""
            raise RuntimeError(f"ffmpeg (distorted) failed: {stderr}")
        if vmaf_result.returncode != 0:
            raise RuntimeError(f"vmaf failed: {vmaf_result.stderr}")

    with open(output_json) as f:
        return json.load(f)


def extract_vmaf_score(vmaf_json: dict) -> float:
    """Extract the mean VMAF score from vmaf JSON output."""
    pooled = vmaf_json.get("pooled_metrics", {})
    vmaf_metric = pooled.get("vmaf", {})
    mean = vmaf_metric.get("mean")
    if mean is not None:
        return mean

    frames = vmaf_json.get("frames", [])
    if frames:
        scores = [f["metrics"]["vmaf"] for f in frames if "vmaf" in f.get("metrics", {})]
        if scores:
            return sum(scores) / len(scores)

    raise ValueError("Could not extract VMAF score from results")
