"""Bot portrait preset loading tests."""

from __future__ import annotations

from pathlib import Path

from bot.image_presets import ImagePresetRepository

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def test_bot_portrait_presets_load() -> None:
    """The portrait pack exposes several distinct male futuristic styles."""
    presets = ImagePresetRepository(CONFIG_DIR)

    assert presets.default == "super_futurama"
    names = [key for key, _ in presets.all()]
    assert names == [
        "super_futurama",
        "quantum_lab",
        "neon_noir",
        "orbital",
        "bio_tech",
        "holo_aristocrat",
        "adult_sfw",
    ]
    prompt = presets.full_prompt("super_futurama")
    assert "Adult man" in prompt
    assert "masculine" in presets.character
    assert "safe for work" in prompt
    assert "no text" in prompt


def test_unknown_preset_raises() -> None:
    """Unknown style keys fail loudly for direct callers."""
    presets = ImagePresetRepository(CONFIG_DIR)
    assert presets.get("missing") is None
