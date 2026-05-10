#!/usr/bin/env python3
"""
Submit Bitmovin Encoding Jobs
==============================
Submits H.265 (HEVC) and AV1 encoding jobs via Bitmovin's Encoding API
using Per-Title encoding for automatic quality optimization.

Prerequisites:
  pip install bitmovin-api-sdk python-dotenv

Usage:
  python submit_bitmovin.py --codec av1                           # all videos, default settings
  python submit_bitmovin.py --codec av1 --video 0                 # specific video
  python submit_bitmovin.py --codec av1 --max-bitrate 3000000     # raise bitrate ceiling
"""

import os
import sys
import argparse
import logging
from dotenv import load_dotenv

load_dotenv()

from datetime import datetime, timezone
from urllib.parse import urlparse

from bitmovin_api_sdk import BitmovinApi, BitmovinApiLogger
from bitmovin_api_sdk.models import (
    HttpsInput,
    H265VideoConfiguration,
    Av1VideoConfiguration,
    Av1PresetConfiguration,

    Encoding,
    Stream,
    StreamInput,
    StreamMode,
    StreamSelectionMode,
    EncodingOutput,
    Fmp4Muxing,
    Mp4Muxing,
    MuxingStream,
    CloudRegion,
    PresetConfiguration,
    AclEntry,
    AclPermission,
    StartEncodingRequest,
    PerTitle,
    H265PerTitleConfiguration,
    Av1PerTitleConfiguration,
)

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────

API_KEY = os.environ.get("BITMOVIN_API_KEY", "<YOUR_API_KEY>")
S3_OUTPUT_ID = os.environ.get("BITMOVIN_S3_OUTPUT_ID", "<YOUR_S3_OUTPUT_ID>")
S3_OUTPUT_BASE_PATH = os.environ.get("BITMOVIN_S3_OUTPUT_BASE_PATH", "encoding-benchmarks/")
VIDEO_URLS_FILE = os.environ.get("BITMOVIN_VIDEO_URLS_FILE", "video_urls.txt")

CODEC_PROFILES = {
    "h265": {
        "label": "H.265 (HEVC)",
        "codec_type": "h265",
    },
    "av1": {
        "label": "AV1",
        "codec_type": "av1",
    },
}

# ─────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("submit")


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def load_video_urls(filepath: str) -> list[str]:
    if not os.path.isfile(filepath):
        log.error(f"Video URLs file not found: {filepath}")
        sys.exit(1)
    urls = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    if not urls:
        log.error(f"No URLs found in {filepath}")
        sys.exit(1)
    log.info(f"Loaded {len(urls)} video URL(s) from {filepath}")
    return urls


def parse_input_url(url: str):
    parsed = urlparse(url)
    host = parsed.hostname
    input_path = parsed.path
    if parsed.query:
        input_path = f"{parsed.path}?{parsed.query}"
    return host, input_path


def _build_encoding_output(output_path: str) -> EncodingOutput:
    return EncodingOutput(
        output_id=S3_OUTPUT_ID,
        output_path=output_path,
        acl=[AclEntry(permission=AclPermission.PRIVATE)],
    )


# ─────────────────────────────────────────────────────────────
# Bitmovin SDK
# ─────────────────────────────────────────────────────────────

def create_api_client(api_key: str) -> BitmovinApi:
    return BitmovinApi(api_key=api_key, logger=BitmovinApiLogger())


def create_https_input(api: BitmovinApi, host: str) -> HttpsInput:
    https_input = HttpsInput(name=f"Input: {host}", host=host)
    return api.encoding.inputs.https.create(https_input=https_input)


def create_h265_config(api: BitmovinApi) -> H265VideoConfiguration:
    config = H265VideoConfiguration(
        name="H.265 Per-Title",
        preset_configuration=PresetConfiguration.VOD_STANDARD,
    )
    return api.encoding.configurations.video.h265.create(
        h265_video_configuration=config
    )


def create_av1_config(api: BitmovinApi) -> Av1VideoConfiguration:
    config = Av1VideoConfiguration(
        name="AV1 Per-Title",
        preset_configuration=Av1PresetConfiguration.VOD_STANDARD,
    )
    return api.encoding.configurations.video.av1.create(
        av1_video_configuration=config
    )



def create_encoding(api: BitmovinApi, name: str) -> Encoding:
    encoding = Encoding(name=name, cloud_region=CloudRegion.AUTO)
    return api.encoding.encodings.create(encoding=encoding)


def create_stream(
    api: BitmovinApi,
    encoding_id: str,
    input_id: str,
    input_path: str,
    codec_config_id: str,
    name: str = "video",
    mode: StreamMode = None,
) -> Stream:
    stream_input = StreamInput(
        input_id=input_id,
        input_path=input_path,
        selection_mode=StreamSelectionMode.AUTO,
    )
    stream = Stream(
        name=name,
        input_streams=[stream_input],
        codec_config_id=codec_config_id,
        mode=mode,
    )
    return api.encoding.encodings.streams.create(
        encoding_id=encoding_id, stream=stream
    )


def create_fmp4_muxing(
    api: BitmovinApi,
    encoding_id: str,
    stream_id: str,
    output_path: str,
) -> Fmp4Muxing:
    muxing = Fmp4Muxing(
        name="fMP4 muxing",
        segment_length=4.0,
        streams=[MuxingStream(stream_id=stream_id)],
        outputs=[_build_encoding_output(output_path)],
    )
    return api.encoding.encodings.muxings.fmp4.create(
        encoding_id=encoding_id, fmp4_muxing=muxing
    )


def create_mp4_muxing(
    api: BitmovinApi,
    encoding_id: str,
    stream_id: str,
    output_path: str,
    filename: str = "output.mp4",
) -> Mp4Muxing:
    muxing = Mp4Muxing(
        name="Progressive MP4 muxing",
        filename=filename,
        streams=[MuxingStream(stream_id=stream_id)],
        outputs=[_build_encoding_output(output_path)],
    )
    return api.encoding.encodings.muxings.mp4.create(
        encoding_id=encoding_id, mp4_muxing=muxing
    )


def start_encoding_per_title(api: BitmovinApi, encoding_id: str, codec_key: str,
                             max_bitrate: int = None, min_bitrate: int = None):
    per_title = PerTitle()
    if codec_key == "h265":
        config = H265PerTitleConfiguration()
        if max_bitrate is not None:
            config.max_bitrate = max_bitrate
        if min_bitrate is not None:
            config.min_bitrate = min_bitrate
        per_title.h265_configuration = config
    elif codec_key == "av1":
        config = Av1PerTitleConfiguration()
        if max_bitrate is not None:
            config.max_bitrate = max_bitrate
        if min_bitrate is not None:
            config.min_bitrate = min_bitrate
        per_title.av1_configuration = config

    start_request = StartEncodingRequest(per_title=per_title)
    api.encoding.encodings.start(
        encoding_id=encoding_id, start_encoding_request=start_request
    )


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

def submit_single_encoding(
    api: BitmovinApi,
    url: str,
    codec_key: str,
    profile: dict,
    video_codec_config_id: str,
    max_bitrate: int = None,
    min_bitrate: int = None,
) -> dict:
    host, input_path = parse_input_url(url)
    video_name = os.path.basename(urlparse(url).path).rsplit(".", 1)[0]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    encoding_name = f"benchmark_{video_name}_{codec_key}_{timestamp}"
    output_path = f"{S3_OUTPUT_BASE_PATH.rstrip('/')}/{encoding_name}"

    # Create HTTPS input
    https_input = create_https_input(api, host)
    log.info(f"  Created HTTPS input: {https_input.id}")

    # Create encoding
    encoding = create_encoding(api, encoding_name)
    log.info(f"  Created encoding: {encoding.id}")

    # Create video stream (Per-Title fixed resolution mode)
    video_stream = create_stream(
        api, encoding.id, https_input.id, input_path,
        video_codec_config_id,
        name=f"{profile['label']} video",
        mode=StreamMode.PER_TITLE_TEMPLATE_FIXED_RESOLUTION,
    )
    log.info(f"  Created video stream: {video_stream.id} (PER_TITLE_TEMPLATE_FIXED_RESOLUTION)")

    # Create progressive MP4 muxing (Per-Title requires {bitrate} placeholder in output path)
    create_mp4_muxing(
        api, encoding.id, video_stream.id,
        f"{output_path}/video/{{bitrate}}/",
        filename="output.mp4",
    )
    log.info(f"  Created MP4 muxing")

    # Start encoding with Per-Title
    start_encoding_per_title(api, encoding.id, codec_key,
                             max_bitrate=max_bitrate, min_bitrate=min_bitrate)
    log.info(f"  Encoding started!")

    return {"encoding_id": encoding.id, "name": encoding_name, "codec": codec_key}


def submit_encodings(codecs: list[str], max_bitrate: int = None,
                     min_bitrate: int = None, video_filter: str = None):
    if API_KEY.startswith("<"):
        log.error("Please set BITMOVIN_API_KEY environment variable.")
        sys.exit(1)
    if S3_OUTPUT_ID.startswith("<"):
        log.error("Please set BITMOVIN_S3_OUTPUT_ID environment variable.")
        sys.exit(1)

    profiles = {k: v for k, v in CODEC_PROFILES.items() if k in codecs}
    if not profiles:
        log.error(f"No valid codecs specified. Choose from: {list(CODEC_PROFILES.keys())}")
        sys.exit(1)

    api = create_api_client(API_KEY)
    video_urls = load_video_urls(VIDEO_URLS_FILE)

    # Create codec configurations for selected codecs
    log.info("Creating codec configurations...")
    codec_config_ids = {}
    if "h265" in profiles:
        h265_config = create_h265_config(api)
        codec_config_ids["h265"] = h265_config.id
        log.info(f"  H.265 config: {h265_config.id}")
    if "av1" in profiles:
        av1_config = create_av1_config(api)
        codec_config_ids["av1"] = av1_config.id
        log.info(f"  AV1 config:   {av1_config.id}")

    # Log Per-Title settings
    log.info(f"Per-Title settings:")
    log.info(f"  max_bitrate: {max_bitrate if max_bitrate is not None else 'default'}")
    log.info(f"  min_bitrate: {min_bitrate if min_bitrate is not None else 'default'}")

    # Filter to specific video if requested
    if video_filter is not None:
        # Match by exact URL or by exact absolute/relative local path
        filter_basename = os.path.basename(video_filter)
        filter_abspath = os.path.abspath(video_filter) if not video_filter.startswith("http") else None
        matched = []
        for u in video_urls:
            url_basename = os.path.basename(urlparse(u).path)
            if u == video_filter:
                matched.append(u)
            elif filter_abspath and os.path.abspath(url_basename) == filter_abspath:
                matched.append(u)
            elif filter_abspath and url_basename == filter_basename:
                # local path provided, match by filename against URL filenames
                matched.append(u)
        if not matched:
            log.error(f"Video not found: {video_filter}")
            log.error(f"Available URLs:")
            for u in video_urls:
                log.error(f"  {u[:80]}...")
            sys.exit(1)
        video_urls = matched

    # Submit all encoding jobs
    log.info("=" * 60)
    log.info("Submitting encoding jobs")
    log.info("=" * 60)

    submitted = []
    for url in video_urls:
        for codec_key, profile in profiles.items():
            video_name = os.path.basename(urlparse(url).path)
            log.info(f"\nVideo: {video_name}")
            log.info(f"Codec: {profile['label']}")

            try:
                info = submit_single_encoding(
                    api, url, codec_key, profile,
                    video_codec_config_id=codec_config_ids[codec_key],
                    max_bitrate=max_bitrate,
                    min_bitrate=min_bitrate,
                )
                submitted.append(info)
            except Exception as e:
                log.error(f"  Failed to submit: {e}")

    # Summary
    log.info("\n" + "=" * 60)
    log.info(f"Submitted {len(submitted)} encoding job(s)")
    log.info("=" * 60)
    for info in submitted:
        log.info(f"  {info['codec']:>5} | {info['encoding_id']} | {info['name']}")
    log.info("\nCheck status in the Bitmovin dashboard or poll via API.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Submit Bitmovin encoding jobs")
    parser.add_argument(
        "--codec", nargs="+", choices=list(CODEC_PROFILES.keys()),
        default=list(CODEC_PROFILES.keys()),
        help="Codecs to encode with (default: all)",
    )
    parser.add_argument(
        "--max-bitrate", type=int, default=None,
        help="Per-Title max bitrate in bps.",
    )
    parser.add_argument(
        "--min-bitrate", type=int, default=None,
        help="Per-Title min bitrate in bps.",
    )
    parser.add_argument(
        "--video", type=str, default=None,
        help="Full URL or full local path of the video to encode. Omit for all.",
    )
    args = parser.parse_args()
    submit_encodings(args.codec, max_bitrate=args.max_bitrate,
                     min_bitrate=args.min_bitrate, video_filter=args.video)
