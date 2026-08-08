"""Hash-based ID generation for issues, dependencies, and comments.

IDs are base36 hashes whose length scales with the item count via
:data:`ID_LENGTH_THRESHOLDS`. Collision rates therefore govern *retries*, not
correctness: every collision is detected against ``existing_ids`` and resolved
by :meth:`IDGenerator.generate_id` with a nonce or, once those are exhausted,
by falling back to ``length + 2``. Reaching a user-visible failure would take
:data:`max_retries` (100) consecutive collisions.

``docs/id-collisions.md`` has the address-space and birthday-paradox
derivation behind the thresholds; ``dcat doctor --check-id-distribution``
reports the live figures for a real database.
"""

from __future__ import annotations

import hashlib
import math
import uuid
from datetime import datetime

from dogcat.constants import DEFAULT_NAMESPACE, ID_LENGTH_MAX, ID_LENGTH_THRESHOLDS


def get_id_length_for_count(issue_count: int) -> int:
    """Determine the appropriate ID length based on issue count.

    Progressive scaling prevents collision likelihood as the database grows:
    - 4 characters for 0-500 issues
    - 5 characters for 501-1500 issues
    - 6 characters for 1501-5000 issues
    - 7 characters beyond that

    ``docs/id-collisions.md`` has the birthday-paradox math behind these
    thresholds.

    Args:
        issue_count: Current number of issues in the database.

    Returns:
        Appropriate ID length (4-7 characters).
    """
    for max_count, length in ID_LENGTH_THRESHOLDS:
        if issue_count <= max_count:
            return length
    return ID_LENGTH_MAX


def address_space(length: int) -> int:
    """Return the size of the base36 address space for IDs of given length.

    Args:
        length: ID length (number of base36 characters).

    Returns:
        ``36 ** length``.
    """
    return 36**length


def collision_probability(issue_count: int, length: int) -> float:
    """Per-generation collision probability for a new hash.

    Approximates the chance that a freshly generated base36 hash of the
    given ``length`` collides with one of the ``issue_count`` existing
    IDs. Exact for uniform sampling when ``issue_count << 36 ** length``.

    Args:
        issue_count: Number of IDs already in the database.
        length: ID length (base36 characters).

    Returns:
        Probability in ``[0.0, 1.0]``.
    """
    if length <= 0 or issue_count <= 0:
        return 0.0
    return min(1.0, issue_count / address_space(length))


def cumulative_collision_probability(issue_count: int, length: int) -> float:
    """Birthday-paradox: probability that *any* collision occurred so far.

    Approximates the chance that during the lifetime of a database with
    ``issue_count`` IDs of the given ``length``, at least one
    ``IDGenerator.generate_id`` call retried because of a hash
    collision.

    Args:
        issue_count: Number of IDs already in the database.
        length: ID length (base36 characters).

    Returns:
        Probability in ``[0.0, 1.0]``.
    """
    if length <= 0 or issue_count <= 1:
        return 0.0
    n = address_space(length)
    return 1.0 - math.exp(-(issue_count**2) / (2 * n))


def _base36_encode(data: bytes) -> str:
    """Encode bytes as base36 (0-9, a-z)."""
    num = int.from_bytes(data, byteorder="big")
    if num == 0:
        return "0"

    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    result: list[str] = []
    while num:
        result.append(digits[num % 36])
        num //= 36
    return "".join(reversed(result))


def generate_hash_id(
    input_data: str,
    nonce: str = "",
    length: int = 4,
) -> str:
    """Generate a hash-based ID from input data.

    Args:
        input_data: Data to hash (e.g., issue title + timestamp)
        nonce: Optional nonce to handle collisions (empty string for first attempt)
        length: Desired length of the hash portion (default: 4)

    Returns:
        Hash string (just the hash portion, no prefix)
    """
    combined = input_data + nonce
    hash_obj = hashlib.sha256(combined.encode())
    hash_bytes = hash_obj.digest()
    hash_str = _base36_encode(hash_bytes)
    return hash_str[:length]


def generate_issue_id(
    title: str,
    timestamp: datetime | None = None,
    nonce: str = "",
    issue_count: int = 0,
) -> str:
    """Generate an ID hash for an issue.

    Args:
        title: Issue title
        timestamp: Timestamp for issue creation (default: now)
        nonce: Optional nonce for collision handling
        issue_count: Current number of issues, used for progressive ID length scaling

    Returns:
        Issue ID hash (without namespace prefix)
    """
    if timestamp is None:
        timestamp = datetime.now().astimezone()

    length = get_id_length_for_count(issue_count)
    # Combine title with timestamp for deterministic hashing
    input_data = f"{title}:{timestamp.isoformat()}"
    return generate_hash_id(input_data, nonce=nonce, length=length)


def generate_dependency_id(
    issue_id: str,
    depends_on_id: str,
    dep_type: str,
    nonce: str = "",
    prefix: str = "dep",
) -> str:
    """Generate an ID for a dependency.

    Args:
        issue_id: ID of the issue with the dependency
        depends_on_id: ID of what it depends on
        dep_type: Type of dependency (blocks, parent-child, related)
        nonce: Optional nonce for collision handling
        prefix: ID prefix (default: "dep")

    Returns:
        Dependency ID (with prefix)
    """
    input_data = f"{issue_id}:{depends_on_id}:{dep_type}"
    hash_id = generate_hash_id(input_data, nonce=nonce, length=4)
    return f"{prefix}-{hash_id}"


def generate_comment_id() -> str:
    """Generate an ID for a comment using UUID.

    Returns:
        Comment ID (UUID format)
    """
    # Use UUID for comments - simpler and less collision-prone
    return str(uuid.uuid4())


class IDGenerator:
    """Manages ID generation with collision detection and handling."""

    def __init__(
        self,
        existing_ids: set[str] | None = None,
        namespace: str = DEFAULT_NAMESPACE,
    ) -> None:
        """Initialize the ID generator.

        Args:
            existing_ids: Set of already-used IDs to detect collisions
            namespace: Default namespace for generated IDs (default: "dc")
        """
        self.existing_ids = existing_ids or set()
        self.namespace = namespace
        self.max_retries = 100
        self._counter = 0

    @property
    def id_length(self) -> int:
        """Get the appropriate ID length based on current issue count."""
        return get_id_length_for_count(len(self.existing_ids))

    def add_existing_id(self, issue_id: str) -> None:
        """Record an existing ID for collision detection.

        Incremental-registration counterpart to the ``existing_ids``
        constructor arg — the public way to register an id after
        construction.
        """
        self.existing_ids.add(issue_id)

    def generate(self) -> str:
        """Generate a simple unique ID using a counter.

        This is useful for demo/test scenarios where deterministic IDs
        based on content aren't needed.

        Returns:
            Unique ID in format "{namespace}-{counter}". Registered in
            ``self.existing_ids`` on the way out — see :meth:`generate_id`
            on why that makes these generators non-repeatable.
        """
        while True:
            self._counter += 1
            candidate_id = f"{self.namespace}-{self._counter:04d}"
            if candidate_id not in self.existing_ids:
                self.existing_ids.add(candidate_id)
                return candidate_id

    def generate_id(
        self,
        title: str,
        timestamp: datetime | None = None,
        namespace: str | None = None,
    ) -> str:
        """Generate a unique ID hash, handling collisions.

        Uses progressive ID length scaling based on current item count
        to proactively prevent collisions as the database grows.

        Args:
            title: Item title (issue or proposal)
            timestamp: Timestamp for creation
            namespace: Namespace for collision checking
                (defaults to instance namespace)

        Returns:
            Unique ID hash (without namespace prefix). Usually ``id_length``
            characters, but both collision fallbacks return ``id_length + 2``
            — callers must not assume a fixed width.

        Not a pure function, despite hashing its inputs: every generator on
        this class registers the minted full id in ``self.existing_ids``, so
        two calls with the identical ``title`` and ``timestamp`` return
        *different* hashes. Reusing one generator across a test that expects
        a stable id will surprise you; construct a fresh one instead.
        """
        if namespace is None:
            namespace = self.namespace
        if timestamp is None:
            timestamp = datetime.now().astimezone()

        length = self.id_length
        input_data = f"{title}:{timestamp.isoformat()}"

        for attempt in range(self.max_retries):
            nonce = "" if attempt == 0 else str(attempt)
            candidate_hash = generate_hash_id(
                input_data,
                nonce=nonce,
                length=length,
            )
            full_id = f"{namespace}-{candidate_hash}"
            if full_id not in self.existing_ids:
                self.existing_ids.add(full_id)
                return candidate_hash

        # If standard length fails, try longer ID (length + 2). Two extra
        # base36 chars widen the keyspace 36**2 = 1296x, so even a saturated
        # standard-length space yields a collision-free ID on this fallback.
        fallback_length = length + 2
        candidate_hash = generate_hash_id(
            input_data,
            nonce="",
            length=fallback_length,
        )
        full_id = f"{namespace}-{candidate_hash}"
        if full_id not in self.existing_ids:
            self.existing_ids.add(full_id)
            return candidate_hash

        # Last resort: use timestamp as nonce with longer length
        candidate_hash = generate_hash_id(
            input_data,
            nonce=str(int(timestamp.timestamp() * 1000000)),
            length=fallback_length,
        )
        full_id = f"{namespace}-{candidate_hash}"
        self.existing_ids.add(full_id)
        return candidate_hash

    # Aliases for domain-specific clarity
    generate_issue_id = generate_id
    generate_proposal_id = generate_id

    def generate_dependency_id(
        self,
        issue_id: str,
        depends_on_id: str,
        dep_type: str,
        prefix: str = "dep",
    ) -> str:
        """Generate a unique dependency ID.

        Args:
            issue_id: ID of the issue with the dependency
            depends_on_id: ID of what it depends on
            dep_type: Type of dependency
            prefix: ID prefix

        Returns:
            Unique dependency ID. The collision fallback hashes at length 6
            regardless of ``id_length``, so the width is not fixed.
            Registered in ``self.existing_ids`` — see :meth:`generate_id`.
        """
        for attempt in range(self.max_retries):
            nonce = "" if attempt == 0 else str(attempt)
            candidate_id = generate_dependency_id(
                issue_id,
                depends_on_id,
                dep_type,
                nonce=nonce,
                prefix=prefix,
            )

            if candidate_id not in self.existing_ids:
                self.existing_ids.add(candidate_id)
                return candidate_id

        # Fallback to longer ID
        input_data = f"{issue_id}:{depends_on_id}:{dep_type}"
        hash_id = generate_hash_id(input_data, nonce="", length=6)
        candidate_id = f"{prefix}-{hash_id}"

        self.existing_ids.add(candidate_id)
        return candidate_id

    def generate_comment_id(self) -> str:
        """Generate a unique comment ID.

        Returns:
            Unique comment ID, registered in ``self.existing_ids`` — see
            :meth:`generate_id`.
        """
        candidate_id = generate_comment_id()
        while candidate_id in self.existing_ids:
            candidate_id = generate_comment_id()
        self.existing_ids.add(candidate_id)
        return candidate_id
