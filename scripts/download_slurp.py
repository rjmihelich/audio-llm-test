#!/usr/bin/env python3
"""Download SLURP dataset and import into the test platform.

Downloads audio + annotations from Zenodo/GitHub, converts FLAC→WAV,
and creates corpus entries + speech sample records in the database.

Usage:
    python scripts/download_slurp.py [--splits test,train,devel] [--headset-only] [--max-per-scenario N]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import tarfile
import uuid
import wave
from pathlib import Path
from urllib.request import urlretrieve

import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SLURP_AUDIO_URL = "https://zenodo.org/record/4274930/files/slurp_real.tar.gz"
SLURP_JSONL_BASE = "https://raw.githubusercontent.com/pswietojanski/slurp/master/dataset/slurp"

DOWNLOAD_DIR = Path(__file__).resolve().parents[1] / "storage" / "slurp"
AUDIO_EXTRACT_DIR = DOWNLOAD_DIR / "audio"
ANNOTATIONS_DIR = DOWNLOAD_DIR / "annotations"
WAV_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "storage" / "audio" / "slurp_real"

# Map SLURP scenarios → our corpus categories
SCENARIO_TO_CATEGORY = {
    "alarm": "general",
    "audio": "media",
    "calendar": "general",
    "cooking": "general",
    "datetime": "general",
    "email": "general",
    "general": "general",
    "iot": "general",
    "lists": "general",
    "music": "media",
    "news": "general",
    "play": "media",
    "qa": "general",
    "recommendation": "general",
    "social": "phone",
    "takeaway": "general",
    "transport": "navigation",
    "weather": "climate",
}


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def _progress_hook(block_num, block_size, total_size):
    downloaded = block_num * block_size
    if total_size > 0:
        pct = min(100, downloaded * 100 / total_size)
        mb = downloaded / 1024 / 1024
        total_mb = total_size / 1024 / 1024
        print(f"\r  {mb:.0f}/{total_mb:.0f} MB ({pct:.1f}%)", end="", flush=True)


def download_audio():
    """Download and extract SLURP real audio (~3.9 GB)."""
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    tarball = DOWNLOAD_DIR / "slurp_real.tar.gz"

    if not tarball.exists():
        logger.info("Downloading SLURP real audio (3.9 GB) ...")
        urlretrieve(SLURP_AUDIO_URL, tarball, reporthook=_progress_hook)
        print()  # newline after progress
        logger.info("Download complete: %s", tarball)
    else:
        logger.info("Tarball already exists: %s", tarball)

    # Extract
    if not AUDIO_EXTRACT_DIR.exists() or not any(AUDIO_EXTRACT_DIR.rglob("*.flac")):
        logger.info("Extracting audio ...")
        AUDIO_EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
        with tarfile.open(tarball, "r:gz") as tar:
            tar.extractall(AUDIO_EXTRACT_DIR)
        logger.info("Extracted to %s", AUDIO_EXTRACT_DIR)
    else:
        logger.info("Audio already extracted: %s", AUDIO_EXTRACT_DIR)


def download_annotations(splits: list[str]):
    """Download SLURP JSONL annotation files from GitHub."""
    ANNOTATIONS_DIR.mkdir(parents=True, exist_ok=True)

    for split in splits:
        dest = ANNOTATIONS_DIR / f"{split}.jsonl"
        if dest.exists():
            logger.info("Annotations already exist: %s", dest)
            continue
        url = f"{SLURP_JSONL_BASE}/{split}.jsonl"
        logger.info("Downloading %s ...", url)
        urlretrieve(url, dest)
        logger.info("Saved: %s", dest)


# ---------------------------------------------------------------------------
# FLAC → WAV conversion
# ---------------------------------------------------------------------------

def flac_to_wav(flac_path: Path, wav_path: Path, target_sr: int = 16000) -> bool:
    """Convert FLAC to 16-bit WAV at target sample rate using ffmpeg."""
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(flac_path),
                "-ar", str(target_sr),
                "-ac", "1",
                "-sample_fmt", "s16",
                str(wav_path),
            ],
            capture_output=True,
            timeout=30,
            check=True,
        )
        return True
    except FileNotFoundError:
        # Try afconvert on macOS
        try:
            subprocess.run(
                [
                    "afconvert",
                    "-f", "WAVE",
                    "-d", f"LEI16@{target_sr}",
                    "-c", "1",
                    str(flac_path),
                    str(wav_path),
                ],
                capture_output=True,
                timeout=30,
                check=True,
            )
            return True
        except Exception as e:
            logger.error("Convert failed for %s: %s", flac_path.name, e)
            return False
    except Exception as e:
        logger.error("Convert failed for %s: %s", flac_path.name, e)
        return False


# ---------------------------------------------------------------------------
# Database import
# ---------------------------------------------------------------------------

async def import_to_db(
    splits: list[str],
    headset_only: bool,
    max_per_scenario: int | None,
):
    """Parse SLURP annotations and create corpus entries + speech samples."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    from backend.app.models.base import async_session
    from backend.app.models.speech import CorpusEntry, SpeechSample, Voice

    # Find all available FLAC files
    flac_files: dict[str, Path] = {}
    for flac_path in AUDIO_EXTRACT_DIR.rglob("*.flac"):
        flac_files[flac_path.name] = flac_path
    logger.info("Found %d FLAC files on disk", len(flac_files))

    if not flac_files:
        logger.error("No FLAC files found in %s — did audio download/extract succeed?", AUDIO_EXTRACT_DIR)
        return

    # Create a synthetic "slurp" voice entry if it doesn't exist
    async with async_session() as session:
        voice_stmt = select(Voice).where(Voice.provider == "slurp")
        existing_voice = (await session.execute(voice_stmt)).scalar_one_or_none()

        if existing_voice is None:
            slurp_voice = Voice(
                provider="slurp",
                voice_id="slurp_real",
                name="SLURP Real Speaker",
                gender="neutral",
                age_group="adult",
                accent="mixed",
                language="en",
            )
            session.add(slurp_voice)
            await session.commit()
            await session.refresh(slurp_voice)
            voice_id = slurp_voice.id
            logger.info("Created SLURP voice record: %s", voice_id)
        else:
            voice_id = existing_voice.id
            logger.info("Using existing SLURP voice: %s", voice_id)

    # Process each split
    total_imported = 0
    total_skipped = 0
    total_converted = 0
    total_failed = 0
    scenario_counts: dict[str, int] = {}

    for split in splits:
        jsonl_path = ANNOTATIONS_DIR / f"{split}.jsonl"
        if not jsonl_path.exists():
            logger.warning("Missing annotation file: %s", jsonl_path)
            continue

        logger.info("Processing split: %s", split)
        entries = []
        with open(jsonl_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))

        logger.info("  %d utterances in %s", len(entries), split)

        async with async_session() as session:
            for entry in entries:
                scenario = entry.get("scenario", "general")
                category = SCENARIO_TO_CATEGORY.get(scenario, "general")
                intent = entry.get("intent", "")
                action = entry.get("action", "")
                sentence = entry.get("sentence", "")
                slurp_id = entry.get("slurp_id", 0)

                if not sentence:
                    continue

                # Cap per scenario
                if max_per_scenario:
                    sc = scenario_counts.get(scenario, 0)
                    if sc >= max_per_scenario:
                        total_skipped += 1
                        continue

                # Pick best recording
                recordings = entry.get("recordings", [])
                if not recordings:
                    total_skipped += 1
                    continue

                # Filter to headset if requested
                if headset_only:
                    recordings = [r for r in recordings if "headset" in r.get("file", "")]

                if not recordings:
                    total_skipped += 1
                    continue

                # Pick the one with lowest WER (best transcription quality)
                best = min(recordings, key=lambda r: r.get("wer", 999))
                flac_name = best["file"]

                if flac_name not in flac_files:
                    total_skipped += 1
                    continue

                flac_path = flac_files[flac_name]
                wav_name = flac_name.replace(".flac", ".wav")
                wav_path = WAV_OUTPUT_DIR / wav_name

                # Convert FLAC → WAV if needed
                if not wav_path.exists():
                    ok = flac_to_wav(flac_path, wav_path)
                    if not ok:
                        total_failed += 1
                        continue
                    total_converted += 1

                # Get WAV duration
                try:
                    with wave.open(str(wav_path), "rb") as wf:
                        duration_s = wf.getnframes() / wf.getframerate()
                        sample_rate = wf.getframerate()
                except Exception:
                    duration_s = 0.0
                    sample_rate = 16000

                # Check if corpus entry already exists for this slurp_id
                existing_ce = (await session.execute(
                    select(CorpusEntry).where(
                        CorpusEntry.text == sentence,
                        CorpusEntry.category == category,
                        CorpusEntry.language == "en",
                    )
                )).scalar_one_or_none()

                if existing_ce is None:
                    corpus_entry = CorpusEntry(
                        text=sentence,
                        category=category,
                        expected_intent=intent,
                        expected_action=action,
                        language="en",
                    )
                    session.add(corpus_entry)
                    await session.flush()
                    ce_id = corpus_entry.id
                else:
                    ce_id = existing_ce.id

                # Check if speech sample already exists
                existing_ss = (await session.execute(
                    select(SpeechSample).where(
                        SpeechSample.corpus_entry_id == ce_id,
                        SpeechSample.voice_id == voice_id,
                    )
                )).scalar_one_or_none()

                if existing_ss is None:
                    sample = SpeechSample(
                        corpus_entry_id=ce_id,
                        voice_id=voice_id,
                        file_path=str(wav_path),
                        duration_s=duration_s,
                        sample_rate=sample_rate,
                        status="ready",
                    )
                    session.add(sample)

                scenario_counts[scenario] = scenario_counts.get(scenario, 0) + 1
                total_imported += 1

                if total_imported % 500 == 0:
                    await session.commit()
                    logger.info("  ... %d imported", total_imported)

            await session.commit()

    logger.info("=" * 60)
    logger.info("SLURP import complete:")
    logger.info("  Imported:  %d utterances", total_imported)
    logger.info("  Converted: %d FLAC → WAV", total_converted)
    logger.info("  Skipped:   %d", total_skipped)
    logger.info("  Failed:    %d conversions", total_failed)
    logger.info("  By scenario:")
    for sc, cnt in sorted(scenario_counts.items(), key=lambda x: -x[1]):
        cat = SCENARIO_TO_CATEGORY.get(sc, "general")
        logger.info("    %-15s → %-15s  %d", sc, cat, cnt)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Download SLURP and import into test platform")
    parser.add_argument(
        "--splits", default="test",
        help="Comma-separated splits to import (test,train,devel). Default: test"
    )
    parser.add_argument(
        "--headset-only", action="store_true",
        help="Only use headset (close-talk) recordings for cleaner audio"
    )
    parser.add_argument(
        "--max-per-scenario", type=int, default=None,
        help="Cap number of utterances per SLURP scenario"
    )
    parser.add_argument(
        "--skip-audio-download", action="store_true",
        help="Skip downloading the 3.9GB audio tarball (use if already downloaded)"
    )
    args = parser.parse_args()

    splits = [s.strip() for s in args.splits.split(",")]

    # Check for ffmpeg or afconvert
    has_ffmpeg = shutil.which("ffmpeg") is not None
    has_afconvert = shutil.which("afconvert") is not None
    if not has_ffmpeg and not has_afconvert:
        logger.error("Need ffmpeg or afconvert (macOS) to convert FLAC→WAV")
        logger.error("Install: brew install ffmpeg")
        sys.exit(1)

    # Step 1: Download annotations (small, fast)
    logger.info("Step 1: Download annotations")
    download_annotations(splits)

    # Step 2: Download audio (big)
    if not args.skip_audio_download:
        logger.info("Step 2: Download audio (3.9 GB)")
        download_audio()
    else:
        logger.info("Step 2: Skipped audio download")

    # Step 3: Import into database
    logger.info("Step 3: Import into database")
    asyncio.run(import_to_db(splits, args.headset_only, args.max_per_scenario))


if __name__ == "__main__":
    main()
