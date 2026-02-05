"""Hash-based ID generation for issues, dependencies, and comments."""

import hashlib
import uuid
from datetime import datetime

from dogcat.constants import ID_LENGTH_MAX, ID_LENGTH_THRESHOLDS


def get_id_length_for_count(issue_count: int) -> int:
    """Determine the appropriate ID length based on issue count.

    Progressive scaling prevents collision likelihood as the database grows:
    - 4 characters for 0-500 issues
    - 5 characters for 501-1500 issues
    - 6 characters for 1501-5000 issues
    - 7 characters beyond that

    Args:
        issue_count: Current number of issues in the database.

    Returns:
        Appropriate ID length (4-7 characters).
    """
    for max_count, length in ID_LENGTH_THRESHOLDS:
        if issue_count <= max_count:
            return length
    return ID_LENGTH_MAX


def _base36_encode(data: bytes) -> str:
    """Encode bytes as base36 (0-9, a-z)."""
    # Convert bytes to int
    num = int.from_bytes(data, byteorder="big")
    # Convert to base36
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
    # Combine input_data with nonce
    combined = input_data + nonce
    # Hash using SHA256
    hash_obj = hashlib.sha256(combined.encode())
    hash_bytes = hash_obj.digest()
    # Encode as base36
    hash_str = _base36_encode(hash_bytes)
    # Take first 'length' characters
    return hash_str[:length]


def generate_issue_id(
    title: str,
    timestamp: datetime | None = None,
    nonce: str = "",
) -> str:
    """Generate an ID hash for an issue.

    Args:
        title: Issue title
        timestamp: Timestamp for issue creation (default: now)
        nonce: Optional nonce for collision handling

    Returns:
        Issue ID hash (without namespace prefix)
    """
    if timestamp is None:
        timestamp = datetime.now().astimezone()

    # Combine title with timestamp for deterministic hashing
    input_data = f"{title}:{timestamp.isoformat()}"
    return generate_hash_id(input_data, nonce=nonce, length=4)


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
        prefix: str = "dc",
    ) -> None:
        """Initialize the ID generator.

        Args:
            existing_ids: Set of already-used IDs to detect collisions
            prefix: Default prefix for generated IDs (default: "dc")
        """
        self.existing_ids = existing_ids or set()
        self.prefix = prefix
        self.max_retries = 100
        self._counter = 0

    @property
    def id_length(self) -> int:
        """Get the appropriate ID length based on current issue count."""
        return get_id_length_for_count(len(self.existing_ids))

    def add_existing_id(self, issue_id: str) -> None:
        """Record an existing ID for collision detection."""
        self.existing_ids.add(issue_id)

    def generate(self) -> str:
        """Generate a simple unique ID using a counter.

        This is useful for demo/test scenarios where deterministic IDs
        based on content aren't needed.

        Returns:
            Unique ID in format "{prefix}-{counter}"
        """
        while True:
            self._counter += 1
            candidate_id = f"{self.prefix}-{self._counter:04d}"
            if candidate_id not in self.existing_ids:
                self.existing_ids.add(candidate_id)
                return candidate_id

    def generate_issue_id(
        self,
        title: str,
        timestamp: datetime | None = None,
        namespace: str | None = None,
    ) -> str:
        """Generate a unique issue ID hash, handling collisions.

        Uses progressive ID length scaling based on current issue count
        to proactively prevent collisions as the database grows.

        Args:
            title: Issue title
            timestamp: Timestamp for issue creation
            namespace: Namespace/prefix for collision checking
                (defaults to instance prefix)

        Returns:
            Unique issue ID hash (without namespace prefix)
        """
        if namespace is None:
            namespace = self.prefix
        if timestamp is None:
            timestamp = datetime.now().astimezone()

        # Get the scaled ID length based on current issue count
        length = self.id_length
        input_data = f"{title}:{timestamp.isoformat()}"

        # Try generating with increasing nonce values
        for attempt in range(self.max_retries):
            nonce = "" if attempt == 0 else str(attempt)
            candidate_hash = generate_hash_id(
                input_data,
                nonce=nonce,
                length=length,
            )
            # Check collision against full ID (namespace-hash)
            full_id = f"{namespace}-{candidate_hash}"
            if full_id not in self.existing_ids:
                self.existing_ids.add(full_id)
                return candidate_hash

        # If standard length fails, try longer ID (length + 2)
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
            Unique dependency ID
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
            Unique comment ID
        """
        candidate_id = generate_comment_id()
        while candidate_id in self.existing_ids:
            candidate_id = generate_comment_id()
        self.existing_ids.add(candidate_id)
        return candidate_id
