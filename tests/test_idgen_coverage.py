"""Additional idgen tests to cover fallback paths."""

from datetime import datetime, timezone

from dogcat.idgen import IDGenerator, generate_hash_id


class TestIDGeneratorGenerate:
    """Test the simple counter-based generate() method."""

    def test_generate_returns_formatted_id(self) -> None:
        """Test that generate() returns IDs in prefix-NNNN format."""
        gen = IDGenerator(prefix="dc")
        id1 = gen.generate()
        assert id1 == "dc-0001"

    def test_generate_increments_counter(self) -> None:
        """Test that generate() increments the counter."""
        gen = IDGenerator(prefix="dc")
        id1 = gen.generate()
        id2 = gen.generate()
        id3 = gen.generate()
        assert id1 == "dc-0001"
        assert id2 == "dc-0002"
        assert id3 == "dc-0003"

    def test_generate_skips_existing_ids(self) -> None:
        """Test that generate() skips existing IDs."""
        gen = IDGenerator(
            existing_ids={"dc-0001", "dc-0002"},
            prefix="dc",
        )
        id1 = gen.generate()
        assert id1 == "dc-0003"
        assert id1 in gen.existing_ids

    def test_generate_tracks_ids(self) -> None:
        """Test that generate() adds new IDs to existing_ids."""
        gen = IDGenerator(prefix="test")
        id1 = gen.generate()
        assert id1 in gen.existing_ids


class TestIDGeneratorIssueFallback:
    """Test IDGenerator.generate_issue_id fallback to longer IDs."""

    def test_fallback_to_longer_id_on_exhaustion(self) -> None:
        """Test that generate_issue_id falls back to longer ID after max retries."""
        gen = IDGenerator(prefix="dc")
        gen.max_retries = 2  # Small retry count to force fallback quickly
        timestamp = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Pre-fill the IDs that the first attempts would generate
        base_input = f"Test:{timestamp.isoformat()}"
        for attempt in range(2):
            nonce = "" if attempt == 0 else str(attempt)
            candidate = generate_hash_id(base_input, nonce=nonce, length=4)
            gen.add_existing_id(f"dc-{candidate}")

        # Now generate should fall back to longer ID (length + 2 = 6)
        result = gen.generate_issue_id("Test", timestamp=timestamp)
        assert len(result) == 6  # Fallback length
        assert f"dc-{result}" in gen.existing_ids

    def test_last_resort_timestamp_nonce(self) -> None:
        """Test last-resort fallback using timestamp as nonce."""
        gen = IDGenerator(prefix="dc")
        gen.max_retries = 1
        timestamp = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        base_input = f"Test:{timestamp.isoformat()}"

        # Fill standard length IDs
        candidate = generate_hash_id(base_input, nonce="", length=4)
        gen.add_existing_id(f"dc-{candidate}")

        # Fill fallback length IDs
        fallback_candidate = generate_hash_id(base_input, nonce="", length=6)
        gen.add_existing_id(f"dc-{fallback_candidate}")

        # Should use timestamp nonce as last resort
        result = gen.generate_issue_id("Test", timestamp=timestamp)
        assert f"dc-{result}" in gen.existing_ids


class TestIDGeneratorDependencyFallback:
    """Test dependency ID fallback to longer IDs."""

    def test_dependency_fallback_to_longer_id(self) -> None:
        """Test dependency ID falls back to longer hash on collision."""
        gen = IDGenerator(prefix="dc")
        gen.max_retries = 1

        # Pre-fill with the first candidate
        from dogcat.idgen import generate_dependency_id

        first = generate_dependency_id("issue1", "issue2", "blocks")
        gen.add_existing_id(first)

        # Now generate should produce a different ID (possibly longer)
        result = gen.generate_dependency_id("issue1", "issue2", "blocks")
        assert result in gen.existing_ids
        assert result != first
