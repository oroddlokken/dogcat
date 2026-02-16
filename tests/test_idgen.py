"""Tests for ID generation module."""

from datetime import datetime, timezone

import pytest

from dogcat.idgen import (
    IDGenerator,
    _base36_encode,
    generate_comment_id,
    generate_dependency_id,
    generate_hash_id,
    generate_issue_id,
    get_id_length_for_count,
)


class TestProgressiveIdLength:
    """Test progressive ID length scaling based on issue count."""

    def test_length_for_small_database(self) -> None:
        """Test that small databases (0-500) use 4-char IDs."""
        assert get_id_length_for_count(0) == 4
        assert get_id_length_for_count(100) == 4
        assert get_id_length_for_count(500) == 4

    def test_length_for_medium_database(self) -> None:
        """Test that medium databases (501-1500) use 5-char IDs."""
        assert get_id_length_for_count(501) == 5
        assert get_id_length_for_count(1000) == 5
        assert get_id_length_for_count(1500) == 5

    def test_length_for_large_database(self) -> None:
        """Test that large databases (1501-5000) use 6-char IDs."""
        assert get_id_length_for_count(1501) == 6
        assert get_id_length_for_count(3000) == 6
        assert get_id_length_for_count(5000) == 6

    def test_length_for_very_large_database(self) -> None:
        """Test that very large databases (>5000) use 7-char IDs."""
        assert get_id_length_for_count(5001) == 7
        assert get_id_length_for_count(10000) == 7
        assert get_id_length_for_count(100000) == 7


class TestBase36Encoding:
    """Test base36 encoding utility."""

    def test_base36_encode_zero(self) -> None:
        """Test encoding zero."""
        result = _base36_encode(b"\x00")
        assert result == "0"

    def test_base36_encode_small_value(self) -> None:
        """Test encoding small values."""
        result = _base36_encode(b"\x01")
        assert result in "0123456789abcdefghijklmnopqrstuvwxyz"

    def test_base36_encode_deterministic(self) -> None:
        """Test that encoding is deterministic."""
        data = b"test"
        result1 = _base36_encode(data)
        result2 = _base36_encode(data)
        assert result1 == result2


class TestGenerateHashId:
    """Test basic hash ID generation."""

    def test_basic_generation(self) -> None:
        """Test generating a basic hash (no prefix)."""
        hash_value = generate_hash_id("test input")
        assert isinstance(hash_value, str)
        # Should be just the hash, no prefix
        assert "-" not in hash_value
        assert len(hash_value) == 4  # Default length

    def test_hash_length(self) -> None:
        """Test that hash has correct length."""
        hash_value = generate_hash_id("test", length=4)
        assert len(hash_value) == 4

    @pytest.mark.parametrize("length", [2, 4, 6, 8])
    def test_custom_length(self, length: int) -> None:
        """Test custom hash length."""
        hash_value = generate_hash_id("test", length=length)
        assert len(hash_value) == length

    def test_deterministic(self) -> None:
        """Test that same input produces same hash."""
        input_data = "issue title"
        hash1 = generate_hash_id(input_data)
        hash2 = generate_hash_id(input_data)
        assert hash1 == hash2

    def test_different_input_different_id(self) -> None:
        """Test that different inputs produce different IDs."""
        id1 = generate_hash_id("input1")
        id2 = generate_hash_id("input2")
        assert id1 != id2

    def test_nonce_changes_id(self) -> None:
        """Test that nonce affects the ID."""
        id1 = generate_hash_id("test", nonce="")
        id2 = generate_hash_id("test", nonce="1")
        assert id1 != id2

    def test_unicode_input(self) -> None:
        """Test handling of unicode characters."""
        hash_value = generate_hash_id("测试 тест مرحبا")
        assert isinstance(hash_value, str)
        assert "-" not in hash_value  # Just hash, no prefix

    def test_special_characters(self) -> None:
        """Test handling of special characters."""
        hash_value = generate_hash_id("test!@#$%^&*()")
        assert isinstance(hash_value, str)
        assert "-" not in hash_value  # Just hash, no prefix


class TestGenerateIssueId:
    """Test issue-specific ID generation."""

    def test_basic_issue_generation(self) -> None:
        """Test generating an issue ID hash (no prefix)."""
        hash_value = generate_issue_id("Fix login bug")
        # Returns just the hash, no prefix
        assert isinstance(hash_value, str)
        assert "-" not in hash_value

    def test_issue_id_deterministic(self) -> None:
        """Test that issue ID is deterministic with same timestamp."""
        timestamp = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        hash1 = generate_issue_id("Test issue", timestamp=timestamp)
        hash2 = generate_issue_id("Test issue", timestamp=timestamp)
        assert hash1 == hash2

    def test_different_timestamps_different_ids(self) -> None:
        """Test that different timestamps produce different IDs."""
        t1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 1, 1, 12, 0, 1, tzinfo=timezone.utc)
        hash1 = generate_issue_id("Test issue", timestamp=t1)
        hash2 = generate_issue_id("Test issue", timestamp=t2)
        assert hash1 != hash2

    def test_issue_id_with_nonce(self) -> None:
        """Test issue ID generation with nonce for collisions."""
        timestamp = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        hash1 = generate_issue_id("Test", timestamp=timestamp, nonce="")
        hash2 = generate_issue_id("Test", timestamp=timestamp, nonce="1")
        assert hash1 != hash2


class TestGenerateDependencyId:
    """Test dependency-specific ID generation."""

    def test_basic_dependency_generation(self) -> None:
        """Test generating a dependency ID."""
        id_value = generate_dependency_id("issue1", "issue2", "blocks")
        assert id_value.startswith("dep-")

    def test_dependency_id_deterministic(self) -> None:
        """Test that dependency ID is deterministic."""
        id1 = generate_dependency_id("issue1", "issue2", "blocks")
        id2 = generate_dependency_id("issue1", "issue2", "blocks")
        assert id1 == id2

    def test_different_params_different_ids(self) -> None:
        """Test that different parameters produce different IDs."""
        id1 = generate_dependency_id("issue1", "issue2", "blocks")
        id2 = generate_dependency_id("issue1", "issue3", "blocks")
        assert id1 != id2

    def test_different_dep_type_different_ids(self) -> None:
        """Test that different dependency types produce different IDs."""
        id1 = generate_dependency_id("issue1", "issue2", "blocks")
        id2 = generate_dependency_id("issue1", "issue2", "parent-child")
        assert id1 != id2

    def test_dependency_id_custom_prefix(self) -> None:
        """Test dependency ID with custom prefix."""
        id_value = generate_dependency_id("issue1", "issue2", "blocks", prefix="link")
        assert id_value.startswith("link-")


class TestGenerateCommentId:
    """Test comment ID generation."""

    def test_comment_id_generation(self) -> None:
        """Test generating a comment ID."""
        id_value = generate_comment_id()
        assert isinstance(id_value, str)
        # Should be UUID format (with dashes)
        assert len(id_value) > 0

    def test_comment_ids_unique(self) -> None:
        """Test that generated comment IDs are unique."""
        id1 = generate_comment_id()
        id2 = generate_comment_id()
        assert id1 != id2


class TestIDGenerator:
    """Test the IDGenerator class with collision handling."""

    def test_generator_initialization(self) -> None:
        """Test creating an IDGenerator."""
        gen = IDGenerator()
        assert len(gen.existing_ids) == 0

    def test_generator_with_existing_ids(self) -> None:
        """Test initializing with existing IDs."""
        existing = {"dc-aaaa", "dc-bbbb"}
        gen = IDGenerator(existing_ids=existing)
        assert "dc-aaaa" in gen.existing_ids
        assert "dc-bbbb" in gen.existing_ids

    def test_id_length_property_empty(self) -> None:
        """Test id_length property with empty database."""
        gen = IDGenerator()
        assert gen.id_length == 4

    def test_id_length_property_scales_with_count(self) -> None:
        """Test that id_length scales based on existing_ids count."""
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
        """Test that generated IDs use the appropriate length."""
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
        """Test adding an existing ID."""
        gen = IDGenerator()
        gen.add_existing_id("dc-test")
        assert "dc-test" in gen.existing_ids

    def test_generate_unique_issue_id(self) -> None:
        """Test that generator produces unique IDs."""
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
        """Test that collision handling uses nonce."""
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
        """Test generating dependency IDs."""
        gen = IDGenerator()
        id1 = gen.generate_dependency_id("issue1", "issue2", "blocks")
        assert id1 in gen.existing_ids
        assert id1.startswith("dep-")

    def test_generate_dependency_id_unique(self) -> None:
        """Test that dependency IDs are unique with collision handling."""
        gen = IDGenerator()
        gen.add_existing_id("dep-aaaa")

        id1 = gen.generate_dependency_id("issue1", "issue2", "blocks")
        # Might get "dep-aaaa" by coincidence, but generator handles it
        assert id1 in gen.existing_ids

    def test_generate_comment_id_unique(self) -> None:
        """Test that comment IDs are unique."""
        gen = IDGenerator()
        id1 = gen.generate_comment_id()
        id2 = gen.generate_comment_id()

        assert id1 != id2
        assert id1 in gen.existing_ids
        assert id2 in gen.existing_ids

    def test_fallback_to_longer_id(self) -> None:
        """Test fallback to longer ID on max retries."""
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
        """Test generating multiple issues with the same title."""
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
        """Test that different ID types don't collide."""
        gen = IDGenerator()

        issue_hash = gen.generate_issue_id("Test")
        dep_id = gen.generate_dependency_id("issue1", "issue2", "blocks")
        comment_id = gen.generate_comment_id()

        # Issue hash doesn't have prefix, others do
        assert f"dc-{issue_hash}" != dep_id
        assert f"dc-{issue_hash}" != comment_id
        assert dep_id != comment_id
