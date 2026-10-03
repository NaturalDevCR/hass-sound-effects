from __future__ import annotations

import pytest
from sound_effects_studio.media import (
    LoudnessMeasurement,
    MediaError,
    ProbeResult,
    build_filter_chain,
    can_copy_verbatim,
    measure_loudness,
    probe,
    render,
)
from sound_effects_studio.models import Profile, Recipe

pytestmark = pytest.mark.studio

STANDARD = Profile(id="standard", name="Standard", target_lufs=-16, true_peak=-1.5, lra=11)


async def test_probe_wav(make_tone):
    result = await probe(make_tone(seconds=3, channels=2))
    assert result.duration == pytest.approx(3.0, abs=0.05)
    assert result.channels == 2
    assert result.sample_rate == 44100
    assert result.codec.startswith("pcm")


async def test_probe_rejects_non_audio(tmp_path):
    path = tmp_path / "x.mp3"
    path.write_bytes(b"not audio")
    with pytest.raises(MediaError):
        await probe(path)


async def test_filter_chain_identity_is_empty():
    assert build_filter_chain(Recipe(), 3.0, None, None) == []


async def test_filter_chain_full():
    recipe = Recipe(
        trim_start=0.5, trim_end=2.5, gain_db=2, fade_in=0.25, fade_out=0.5, profile_id="standard"
    )
    measured = LoudnessMeasurement(-30, -10, 5, -40, 0.5)
    assert build_filter_chain(recipe, 3.0, STANDARD, measured) == [
        "atrim=start=0.500:end=2.500",
        "asetpts=PTS-STARTPTS",
        "loudnorm=I=-16:TP=-1.5:LRA=11:measured_I=-30:measured_TP=-10:measured_LRA=5:measured_thresh=-40:offset=0.5:linear=true",
        "aresample=44100",
        "volume=2.00dB",
        "afade=t=in:st=0:d=0.250",
        "afade=t=out:st=1.500:d=0.500",
        "alimiter=limit=0.8414:level=0",
    ]


async def test_filter_chain_negative_gain_no_limiter():
    assert build_filter_chain(Recipe(gain_db=-3), 3, None, None) == ["volume=-3.00dB"]


async def test_can_copy_verbatim():
    assert can_copy_verbatim(ProbeResult("mp3", "mp3", 3, 44100, 2), Recipe())
    assert not can_copy_verbatim(ProbeResult("wav", "pcm_s16le", 3, 44100, 2), Recipe())
    assert not can_copy_verbatim(ProbeResult("mp3", "mp3", 3, 44100, 2), Recipe(gain_db=1))


async def test_render_trim_and_fade_duration(make_tone, tmp_path):
    src = make_tone(seconds=5)
    dst = tmp_path / "trim.mp3"
    await render(
        src,
        dst,
        recipe=Recipe(trim_start=1, trim_end=3, fade_in=0.1, fade_out=0.1),
        duration=5,
        channels=2,
        profile=None,
    )
    info = await probe(dst)
    assert info.duration == pytest.approx(2.0, abs=0.06)
    assert info.codec == "mp3"
    assert info.sample_rate == 44100


async def test_render_normalizes_two_levels_close_together(make_tone, tmp_path):
    results = []
    for name, level in (("quiet.wav", -30), ("loud.wav", -8)):
        src = make_tone(name=name, seconds=3, volume_db=level)
        dst = tmp_path / f"{name}.mp3"
        await render(
            src, dst, recipe=Recipe(profile_id="standard"), duration=3, channels=2, profile=STANDARD
        )
        results.append(await measure_loudness(dst, profile=STANDARD))
    assert results[0].input_i == pytest.approx(-16, abs=1.0)
    assert results[1].input_i == pytest.approx(-16, abs=1.0)
    assert results[0].input_i == pytest.approx(results[1].input_i, abs=1.0)


async def test_render_mono_stays_mono(make_tone, tmp_path):
    src = make_tone(seconds=2, channels=1)
    dst = tmp_path / "mono.mp3"
    await render(src, dst, recipe=Recipe(), duration=2, channels=1, profile=None)
    assert (await probe(dst)).channels == 1


async def test_render_failure_raises_media_error(tmp_path):
    src, dst = tmp_path / "bad.wav", tmp_path / "bad.mp3"
    src.write_text("not media")
    with pytest.raises(MediaError):
        await render(src, dst, recipe=Recipe(), duration=1, channels=2, profile=None)
    assert not dst.exists()


async def test_render_reports_progress(make_tone, tmp_path):
    src, dst = make_tone(seconds=2), tmp_path / "progress.mp3"
    progress = []
    await render(
        src, dst, recipe=Recipe(), duration=2, channels=2, profile=None, on_progress=progress.append
    )
    assert progress and progress[-1] >= 0.9
