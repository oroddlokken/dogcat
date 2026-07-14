"""Tests for ID generation module."""

import math
from datetime import datetime, timezone

import pytest

from dogcat.idgen import (
    IDGenerator,
    _base36_encode,
    address_space,
    collision_probability,
    cumulative_collision_probability,
    generate_comment_id,
    generate_dependency_id,
    generate_hash_id,
    generate_issue_id,
    get_id_length_for_count,
)


class TestCollisionMath:
    """Test the collision-probability helpers backing dcat doctor."""

    def test_address_space_grows_36x_per_char(self) -> None:
        """Address space follows N = 36**L exactly."""
        assert address_space(4) == 36**4
        assert address_space(5) == 36**5
        assert address_space(6) == 36**6
        assert address_space(7) == 36**7

    def test_collision_probability_matches_k_over_n(self) -> None:
        """Per-generation probability is k / N for k << N."""
        # k=500 in N=36**4 ≈ 0.0298%
        assert math.isclose(collision_probability(500, 4), 500 / (36**4))
        assert math.isclose(collision_probability(1500, 5), 1500 / (36**5))

    def test_collision_probability_clamped_at_one(self) -> None:
        """If k exceeds N the probability saturates to 1.0."""
        assert collision_probability(10**9, 3) == 1.0

    def test_collision_probability_zero_for_empty_inputs(self) -> None:
        """Zero or negative inputs return a probability of 0.0."""
        assert collision_probability(0, 4) == 0.0
        assert collision_probability(100, 0) == 0.0
        assert collision_probability(-1, 4) == 0.0

    def test_cumulative_increases_with_count(self) -> None:
        """Cumulative birthday-paradox probability is monotonically increasing."""
        p_500 = cumulative_collision_probability(500, 4)
        p_1000 = cumulative_collision_probability(1000, 4)
        p_1500 = cumulative_collision_probability(1500, 4)
        assert 0 < p_500 < p_1000 < p_1500 < 1

    def test_cumulative_under_target_at_thresholds(self) -> None:
        """Each ID-length band stays under its empirical safety margin.

        The bands are documented in the idgen module docstring and these
        bounds are the contract callers can rely on.
        """
        # 500 issues at L=4 -> ~7.17%
        assert cumulative_collision_probability(500, 4) < 0.10
        # 1500 issues at L=5 -> ~1.85%
        assert cumulative_collision_probability(1500, 5) < 0.05
        # 5000 issues at L=6 -> ~0.572%
        assert cumulative_collision_probability(5000, 6) < 0.01

    def test_cumulative_zero_for_empty_inputs(self) -> None:
        """Edge cases mirror collision_probability."""
        assert cumulative_collision_probability(0, 4) == 0.0
        assert cumulative_collision_probability(1, 4) == 0.0
        assert cumulative_collision_probability(100, 0) == 0.0


class TestProgressiveIdLength:
    """ID length scales up in bands as the issue count grows."""

    def test_length_for_small_database(self) -> None:
        """Counts 0-500 map to 4-char IDs."""
        assert get_id_length_for_count(0) == 4
        assert get_id_length_for_count(100) == 4
        assert get_id_length_for_count(500) == 4

    def test_length_for_medium_database(self) -> None:
        """Counts 501-1500 map to 5-char IDs."""
        assert get_id_length_for_count(501) == 5
        assert get_id_length_for_count(1000) == 5
        assert get_id_length_for_count(1500) == 5

    def test_length_for_large_database(self) -> None:
        """Counts 1501-5000 map to 6-char IDs."""
        assert get_id_length_for_count(1501) == 6
        assert get_id_length_for_count(3000) == 6
        assert get_id_length_for_count(5000) == 6

    def test_length_for_very_large_database(self) -> None:
        """Counts above 5000 map to 7-char IDs."""
        assert get_id_length_for_count(5001) == 7
        assert get_id_length_for_count(10000) == 7
        assert get_id_length_for_count(100000) == 7


class TestBase36Encoding:
    """_base36_encode maps bytes to lowercase base36 digits."""

    def test_base36_encode_zero(self) -> None:
        """A zero byte encodes to the single digit '0', not empty."""
        result = _base36_encode(b"\x00")
        assert result == "0"

    def test_base36_encode_small_value(self) -> None:
        """A small byte encodes to a single valid base36 digit."""
        result = _base36_encode(b"\x01")
        assert result in "0123456789abcdefghijklmnopqrstuvwxyz"

    def test_base36_encode_deterministic(self) -> None:
        """The same bytes always encode to the same string."""
        data = b"test"
        result1 = _base36_encode(data)
        result2 = _base36_encode(data)
        assert result1 == result2


class TestGenerateHashId:
    """generate_hash_id returns a bare base36 hash with no prefix."""

    def test_basic_generation(self) -> None:
        """A hash is a 4-char string carrying no namespace prefix."""
        hash_value = generate_hash_id("test input")
        assert isinstance(hash_value, str)
        # Should be just the hash, no prefix
        assert "-" not in hash_value
        assert len(hash_value) == 4  # Default length

    def test_hash_length(self) -> None:
        """length=4 yields a 4-character hash."""
        hash_value = generate_hash_id("test", length=4)
        assert len(hash_value) == 4

    @pytest.mark.parametrize("length", [2, 4, 6, 8])
    def test_custom_length(self, length: int) -> None:
        """The output length matches the requested length."""
        hash_value = generate_hash_id("test", length=length)
        assert len(hash_value) == length

    def test_deterministic(self) -> None:
        """The same input always hashes to the same value."""
        input_data = "issue title"
        hash1 = generate_hash_id(input_data)
        hash2 = generate_hash_id(input_data)
        assert hash1 == hash2

    def test_different_input_different_id(self) -> None:
        """Different inputs hash to different IDs."""
        id1 = generate_hash_id("input1")
        id2 = generate_hash_id("input2")
        assert id1 != id2

    def test_nonce_changes_id(self) -> None:
        """Changing the nonce changes the hash for identical input."""
        id1 = generate_hash_id("test", nonce="")
        id2 = generate_hash_id("test", nonce="1")
        assert id1 != id2

    def test_unicode_input(self) -> None:
        """Non-ASCII input hashes without error to a bare hash."""
        hash_value = generate_hash_id("测试 тест مرحبا")
        assert isinstance(hash_value, str)
        assert "-" not in hash_value  # Just hash, no prefix

    def test_special_characters(self) -> None:
        """Punctuation-heavy input hashes without error to a bare hash."""
        hash_value = generate_hash_id("test!@#$%^&*()")
        assert isinstance(hash_value, str)
        assert "-" not in hash_value  # Just hash, no prefix


class TestGenerateIssueId:
    """generate_issue_id derives a hash from title and timestamp."""

    def test_basic_issue_generation(self) -> None:
        """An issue hash is a bare string with no namespace prefix."""
        hash_value = generate_issue_id("Fix login bug")
        # Returns just the hash, no prefix
        assert isinstance(hash_value, str)
        assert "-" not in hash_value

    def test_issue_id_deterministic(self) -> None:
        """The same title and timestamp yield the same hash."""
        timestamp = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        hash1 = generate_issue_id("Test issue", timestamp=timestamp)
        hash2 = generate_issue_id("Test issue", timestamp=timestamp)
        assert hash1 == hash2

    def test_different_timestamps_different_ids(self) -> None:
        """A one-second timestamp difference changes the hash."""
        t1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 1, 1, 12, 0, 1, tzinfo=timezone.utc)
        hash1 = generate_issue_id("Test issue", timestamp=t1)
        hash2 = generate_issue_id("Test issue", timestamp=t2)
        assert hash1 != hash2

    def test_issue_id_with_nonce(self) -> None:
        """A nonce changes the hash so collisions can be broken."""
        timestamp = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        hash1 = generate_issue_id("Test", timestamp=timestamp, nonce="")
        hash2 = generate_issue_id("Test", timestamp=timestamp, nonce="1")
        assert hash1 != hash2


class TestGenerateDependencyId:
    """generate_dependency_id derives a dep- ID from endpoints and type."""

    def test_basic_dependency_generation(self) -> None:
        """A dependency ID carries the 'dep-' prefix."""
        id_value = generate_dependency_id("issue1", "issue2", "blocks")
        assert id_value.startswith("dep-")

    def test_dependency_id_deterministic(self) -> None:
        """The same endpoints and type yield the same ID."""
        id1 = generate_dependency_id("issue1", "issue2", "blocks")
        id2 = generate_dependency_id("issue1", "issue2", "blocks")
        assert id1 == id2

    def test_different_params_different_ids(self) -> None:
        """A different target endpoint yields a different ID."""
        id1 = generate_dependency_id("issue1", "issue2", "blocks")
        id2 = generate_dependency_id("issue1", "issue3", "blocks")
        assert id1 != id2

    def test_different_dep_type_different_ids(self) -> None:
        """The dependency type is part of the ID's identity."""
        id1 = generate_dependency_id("issue1", "issue2", "blocks")
        id2 = generate_dependency_id("issue1", "issue2", "parent-child")
        assert id1 != id2

    def test_dependency_id_custom_prefix(self) -> None:
        """A custom prefix replaces the default 'dep-'."""
        id_value = generate_dependency_id("issue1", "issue2", "blocks", prefix="link")
        assert id_value.startswith("link-")


class TestGenerateCommentId:
    """generate_comment_id returns a unique UUID-style id."""

    def test_comment_id_generation(self) -> None:
        """A comment ID is a non-empty string."""
        id_value = generate_comment_id()
        assert isinstance(id_value, str)
        # Should be UUID format (with dashes)
        assert len(id_value) > 0

    def test_comment_ids_unique(self) -> None:
        """Two generated comment IDs are never equal."""
        id1 = generate_comment_id()
        id2 = generate_comment_id()
        assert id1 != id2


class TestIDGenerator:
    """Test the IDGenerator class with collision handling."""

    def test_generator_initialization(self) -> None:
        """A fresh generator starts with no known IDs."""
        gen = IDGenerator()
        assert len(gen.existing_ids) == 0

    def test_generator_with_existing_ids(self) -> None:
        """Seeded IDs are present in existing_ids."""
        existing = {"dc-aaaa", "dc-bbbb"}
        gen = IDGenerator(existing_ids=existing)
        assert "dc-aaaa" in gen.existing_ids
        assert "dc-bbbb" in gen.existing_ids

    def test_id_length_property_empty(self) -> None:
        """An empty generator reports a 4-char id_length."""
        gen = IDGenerator()
        assert gen.id_length == 4

    def test_id_length_property_scales_with_count(self) -> None:
        """id_length grows to 5 then 6 as existing_ids crosses each band."""
        # Small database: 4 chars
        gen_small = IDGenerator(existing_ids={f"dc-{i:04d}" for i in range(100)})
        assert gen_small.id_length == 4

        # Medium database: 5 chars
        gen_medium = IDGenerator(existing_ids={f"dc-{i:04d}" for i in range(501)})
        assert gen_medium.id_length == 5

        # Large database: 6 chars
        gen_large = IDGenerator(existing_ids={f"dc-{i:04d}" for i in range(1501)})
        assert gen_large.id_length == 6

    def test_generated_id_uses_scaled_length(self) -> None:
        """A generated hash's length matches the current count band."""
        timestamp = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Small database: 4 chars
        gen_small = IDGenerator(existing_ids={f"dc-{i:04d}" for i in range(100)})
        hash_small = gen_small.generate_issue_id("Test", timestamp=timestamp)
        # Returns just the hash, no prefix
        assert len(hash_small) == 4

        # Medium database: 5 chars
        gen_medium = IDGenerator(existing_ids={f"dc-{i:04d}" for i in range(501)})
        hash_medium = gen_medium.generate_issue_id("Test", timestamp=timestamp)
        assert len(hash_medium) == 5

    def test_add_existing_id(self) -> None:
        """add_existing_id registers the id for collision checks."""
        gen = IDGenerator()
        gen.add_existing_id("dc-test")
        assert "dc-test" in gen.existing_ids

    def test_generate_unique_issue_id(self) -> None:
        """Repeat titles get distinct hashes via collision retry."""
        gen = IDGenerator()
        timestamp = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Generate multiple IDs with collision detection
        hash1 = gen.generate_issue_id("Test", timestamp=timestamp)
        # Full ID is stored in existing_ids
        assert f"dc-{hash1}" in gen.existing_ids

        # Generate again with same input - should get new ID due to collision
        hash2 = gen.generate_issue_id("Test", timestamp=timestamp)
        assert f"dc-{hash2}" in gen.existing_ids
        assert hash1 != hash2

    def test_collision_handling_with_nonce(self) -> None:
        """A pre-seeded collision forces a different hash."""
        gen = IDGenerator()
        # Add a collision manually
        gen.add_existing_id("dc-aaaa")

        timestamp = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        new_hash = gen.generate_issue_id("Test", timestamp=timestamp)

        # Should get a different ID
        assert new_hash != "aaaa"
        # Full ID should be in existing_ids
        assert f"dc-{new_hash}" in gen.existing_ids

    def test_generate_dependency_id(self) -> None:
        """The generated dep- ID is registered in existing_ids."""
        gen = IDGenerator()
        id1 = gen.generate_dependency_id("issue1", "issue2", "blocks")
        assert id1 in gen.existing_ids
        assert id1.startswith("dep-")

    def test_generate_dependency_id_unique(self) -> None:
        """A pre-seeded dep collision still yields a registered ID."""
        gen = IDGenerator()
        gen.add_existing_id("dep-aaaa")

        id1 = gen.generate_dependency_id("issue1", "issue2", "blocks")
        # Might get "dep-aaaa" by coincidence, but generator handles it
        assert id1 in gen.existing_ids

    def test_generate_comment_id_unique(self) -> None:
        """Two generated comment IDs differ and both are registered."""
        gen = IDGenerator()
        id1 = gen.generate_comment_id()
        id2 = gen.generate_comment_id()

        assert id1 != id2
        assert id1 in gen.existing_ids
        assert id2 in gen.existing_ids

    def test_fallback_to_longer_id(self) -> None:
        """A saturated short space still yields a unique registered ID."""
        gen = IDGenerator()
        timestamp = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Create a collision scenario by filling the collision space
        # This is hard to trigger with short IDs, but the code should handle it
        for i in range(100):
            candidate = f"dc-{'a' * (i % 4 + 1)}"
            gen.add_existing_id(candidate)

        # This should still generate a unique ID
        hash_value = gen.generate_issue_id("Test", timestamp=timestamp)
        # Full ID is stored in existing_ids
        assert f"dc-{hash_value}" in gen.existing_ids


class TestIDGeneratorIntegration:
    """Integration tests for ID generation."""

    def test_workflow_with_multiple_issues(self) -> None:
        """Three same-title issues get three distinct registered hashes."""
        gen = IDGenerator()
        timestamp = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Generate multiple issues with same title but different times
        hash1 = gen.generate_issue_id("Test issue", timestamp=timestamp)
        hash2 = gen.generate_issue_id("Test issue", timestamp=timestamp)
        hash3 = gen.generate_issue_id("Test issue", timestamp=timestamp)

        # All should be unique
        assert len({hash1, hash2, hash3}) == 3
        # Full IDs are stored in existing_ids
        assert all(f"dc-{h}" in gen.existing_ids for h in [hash1, hash2, hash3])

    def test_issue_and_dependency_ids_not_colliding(self) -> None:
        """Issue, dependency, and comment IDs are mutually distinct."""
        gen = IDGenerator()

        issue_hash = gen.generate_issue_id("Test")
        dep_id = gen.generate_dependency_id("issue1", "issue2", "blocks")
        comment_id = gen.generate_comment_id()

        # Issue hash doesn't have prefix, others do
        assert f"dc-{issue_hash}" != dep_id
        assert f"dc-{issue_hash}" != comment_id
        assert dep_id != comment_id
