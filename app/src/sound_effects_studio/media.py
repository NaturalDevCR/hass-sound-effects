"""Async ffmpeg helpers used to inspect and render sound effects."""

from __future__ import annotations

import asyncio
import json
import math
import os
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .models import Profile, Recipe

FFMPEG = os.environ.get("SOUND_EFFECTS_FFMPEG", "ffmpeg")
FFPROBE = os.environ.get("SOUND_EFFECTS_FFPROBE", "ffprobe")
SUPPORTED_EXTENSIONS = frozenset(
    {".mp3", ".wav", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".webm", ".mp4", ".mov"}
)


class MediaError(Exception):
    """An ffmpeg or ffprobe operation failed."""


@dataclass(frozen=True)
class ProbeResult:
    format: str
    codec: str
    duration: float
    sample_rate: int
    channels: int


@dataclass(frozen=True)
class LoudnessMeasurement:
    input_i: float
    input_tp: float
    input_lra: float
    input_thresh: float
    target_offset: float


async def _run(*args: str) -> tuple[int, bytes, bytes]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
    except OSError as exc:
        raise MediaError(f"could not run {args[0]}: {exc}") from exc
    return proc.returncode or 0, stdout, stderr


async def probe(path: Path) -> ProbeResult:
    code, stdout, stderr = await _run(
        FFPROBE,
        "-v",
        "error",
        "-show_entries",
        "format=format_name,duration:stream=codec_type,codec_name,sample_rate,channels",
        "-of",
        "json",
        str(path),
    )
    if code:
        raise MediaError(stderr.decode(errors="replace")[-2000:] or "ffprobe failed")
    try:
        data = json.loads(stdout)
        stream = next(s for s in data["streams"] if s.get("codec_type") == "audio")
        fmt = data["format"]
        return ProbeResult(
            format=fmt["format_name"].split(",", 1)[0],
            codec=stream["codec_name"],
            duration=float(fmt["duration"]),
            sample_rate=int(stream["sample_rate"]),
            channels=int(stream["channels"]),
        )
    except (KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MediaError("file has no readable audio stream") from exc


def _trim_filters(trim_start: float, trim_end: float | None, duration: float) -> list[str]:
    end = trim_end if trim_end is not None else duration
    if trim_start > 0 or end < duration - 0.0005:
        return [f"atrim=start={trim_start:.3f}:end={end:.3f}", "asetpts=PTS-STARTPTS"]
    return []


def _number(value: object, fallback: float) -> float:
    try:
        result = float(str(value))
    except ValueError:
        return fallback
    return result if math.isfinite(result) else fallback


async def measure_loudness(
    path: Path,
    *,
    trim_start: float = 0.0,
    trim_end: float | None = None,
    profile: Profile | None = None,
) -> LoudnessMeasurement:
    target_i, target_tp, target_lra = (
        (profile.target_lufs, profile.true_peak, profile.lra) if profile else (-16.0, -1.5, 11.0)
    )
    duration = (await probe(path)).duration
    filters = _trim_filters(trim_start, trim_end, duration)
    filters.append(f"loudnorm=I={target_i:g}:TP={target_tp:g}:LRA={target_lra:g}:print_format=json")
    code, _, stderr = await _run(
        FFMPEG,
        "-hide_banner",
        "-nostats",
        "-i",
        str(path),
        "-af",
        ",".join(filters),
        "-f",
        "null",
        "-",
    )
    text = stderr.decode(errors="replace")
    start, end = text.rfind("{"), text.rfind("}")
    if code or start < 0 or end < start:
        raise MediaError(text[-2000:] or "loudness measurement failed")
    try:
        values = json.loads(text[start : end + 1])
        return LoudnessMeasurement(
            _number(values["input_i"], -70.0),
            _number(values["input_tp"], -70.0),
            _number(values["input_lra"], 0.0),
            _number(values["input_thresh"], -70.0),
            _number(values["target_offset"], 0.0),
        )
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise MediaError("could not parse loudnorm measurement") from exc


def build_filter_chain(
    recipe: Recipe,
    duration: float,
    profile: Profile | None,
    measured: LoudnessMeasurement | None,
) -> list[str]:
    end = recipe.trim_end if recipe.trim_end is not None else duration
    chain = _trim_filters(recipe.trim_start, recipe.trim_end, duration)
    if profile and measured:
        chain.extend(
            [
                f"loudnorm=I={profile.target_lufs:g}:TP={profile.true_peak:g}:LRA={profile.lra:g}:"
                f"measured_I={measured.input_i:g}:measured_TP={measured.input_tp:g}:"
                f"measured_LRA={measured.input_lra:g}:measured_thresh={measured.input_thresh:g}:"
                f"offset={measured.target_offset:g}:linear=true",
                "aresample=44100",
            ]
        )
    if recipe.gain_db != 0:
        chain.append(f"volume={recipe.gain_db:.2f}dB")
    clip = end - recipe.trim_start
    if recipe.fade_in > 0:
        chain.append(f"afade=t=in:st=0:d={recipe.fade_in:.3f}")
    if recipe.fade_out > 0:
        chain.append(
            f"afade=t=out:st={max(0.0, clip - recipe.fade_out):.3f}:d={recipe.fade_out:.3f}"
        )
    if recipe.gain_db > 0 or profile is not None:
        ceiling = profile.true_peak if profile else -1.0
        chain.append(f"alimiter=limit={10 ** (ceiling / 20):.4f}:level=0")
    return chain


def can_copy_verbatim(info: ProbeResult, recipe: Recipe) -> bool:
    return info.codec == "mp3" and recipe.is_identity()


async def render(
    src: Path,
    dst: Path,
    *,
    recipe: Recipe,
    duration: float,
    channels: int,
    profile: Profile | None,
    on_progress: Callable[[float], None] | None = None,
    timeout: float | None = None,
) -> None:
    measured = None
    if profile:
        measured = await measure_loudness(
            src, trim_start=recipe.trim_start, trim_end=recipe.trim_end, profile=profile
        )
    chain = build_filter_chain(recipe, duration, profile, measured)
    clip = (recipe.trim_end if recipe.trim_end is not None else duration) - recipe.trim_start
    args = [FFMPEG, "-hide_banner", "-nostats", "-y", "-i", str(src), "-vn", "-map", "0:a:0"]
    if chain:
        args.extend(["-af", ",".join(chain)])
    args.extend(
        [
            "-ac",
            str(min(channels, 2)),
            "-ar",
            "44100",
            "-c:a",
            "libmp3lame",
            "-q:a",
            "2",
            "-progress",
            "pipe:1",
            str(dst),
        ]
    )
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
    except OSError as exc:
        raise MediaError(f"could not run ffmpeg: {exc}") from exc
    stderr_tail: deque[bytes] = deque(maxlen=80)

    async def read_stderr() -> None:
        assert proc.stderr is not None
        while chunk := await proc.stderr.readline():
            stderr_tail.append(chunk)

    async def consume() -> int:
        assert proc.stdout is not None
        stderr_task = asyncio.create_task(read_stderr())
        async for raw in proc.stdout:
            line = raw.decode(errors="replace").strip()
            if line.startswith("out_time_ms=") and on_progress is not None:
                try:
                    value = float(line.split("=", 1)[1]) / 1_000_000 / clip
                    on_progress(min(1.0, max(0.0, value)))
                except (ValueError, ZeroDivisionError):
                    pass
        result = await proc.wait()
        await stderr_task
        return result

    try:
        code = await asyncio.wait_for(
            consume(), timeout if timeout is not None else max(60, 4 * duration)
        )
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise MediaError("render timed out") from exc
    if code:
        tail = b"".join(stderr_tail).decode(errors="replace")[-2000:]
        raise MediaError(tail or "ffmpeg render failed")
