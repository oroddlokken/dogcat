"""Tests for namespace slug derivation from directory names."""

from __future__ import annotations

import pytest

from dogcat.namespace_slug import slug_from_dir


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # Norwegian
        ("læring", "laering"),
        ("tøffel", "toeffel"),
        ("åpen", "aapen"),
        ("Læring", "laering"),
        ("ØYE", "oeye"),
        # German
        ("über", "ueber"),
        ("schön", "schoen"),
        ("groß", "gross"),
        # Other accented (NFKD strip handles these)
        ("café", "cafe"),
        ("piñata", "pinata"),
        # Already-clean ASCII
        ("dogcat", "dogcat"),
        ("caddy-dns-gigahost", "caddy-dns-gigahost"),
        ("Min-SuperApp", "min-superapp"),
        # Mixed punctuation
        ("ren.no", "ren-no"),
        ("foo_bar", "foo-bar"),
        ("a/b/c", "a-b-c"),
        ("  spaces  ", "spaces"),
        # Leading/trailing dashes
        ("-foo-", "foo"),
        ("--foo--bar--", "foo-bar"),
        # Mixed nordic + space
        ("ä la carte", "ae-la-carte"),
    ],
)
def test_slug_from_dir_known_inputs(name: str, expected: str) -> None:
    """Verify slug from dir known inputs."""
    assert slug_from_dir(name) == expected


@pytest.mark.parametrize(
    "name",
    [
        "",
        "   ",
        "---",
        "测试",  # CJK strips to empty
        "🎉",  # Emoji strips to empty
    ],
)
def test_slug_from_dir_returns_none_for_unsluggable(name: str) -> None:
    """Verify slug from dir returns none for unsluggable."""
    assert slug_from_dir(name) is None
