import hashlib
import json
import logging
import re
import sqlite3
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

logger = logging.getLogger(__name__)


def normalize_url(url: str) -> str:
    """
    Normalize URL for consistent hashing and comparison.
    Args:
        url (str): Original URL
    Returns:
        str: Normalized URL
    """
    if not url:
        return ""

    # Parse the URL
    parsed = urlparse(url.strip())

    # Handle file:// URLs specially (keep as-is but normalize path)
    if parsed.scheme == "file":
        return url.lower().rstrip("/")

    # Normalize scheme to lowercase
    scheme = parsed.scheme.lower() if parsed.scheme else "https"

    # Normalize hostname to lowercase and remove www prefix
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    if hostname.startswith("www."):
        hostname = hostname[4:]

    # Keep port if it's not default
    port = ""
    if parsed.port:
        default_ports = {"http": 80, "https": 443}
        if parsed.port != default_ports.get(scheme):
            port = f":{parsed.port}"

    # Normalize path - remove trailing slash unless it's the root
    path = parsed.path.rstrip("/") if parsed.path != "/" else "/"

    # Sort query parameters for consistency
    query = ""
    if parsed.query:
        params = parse_qs(parsed.query)
        sorted_params = sorted(params.items())
        query = "?" + urlencode(sorted_params, doseq=True)

    # Fragment is typically not needed for comparison
    fragment = f"#{parsed.fragment}" if parsed.fragment else ""

    # Reconstruct normalized URL
    normalized = f"{scheme}://{hostname}{port}{path}{query}{fragment}"
    return normalized


def generate_url_hash(old_url: str, new_url: str = None) -> str:
    """
    Generate a unique hash for URL combination.
    Args:
        old_url (str): Original URL
        new_url (str): New URL (optional)
    Returns:
        str: Hash string for use as primary key
    """
    # Normalize URLs
    old_normalized = normalize_url(old_url)
    new_normalized = normalize_url(new_url) if new_url else ""

    # Create combination string
    combination = f"{old_normalized}|{new_normalized}"

    # Generate SHA-256 hash
    hash_obj = hashlib.sha256(combination.encode("utf-8"))
    hash_str = hash_obj.hexdigest()

    # Return first 16 characters for readability
    return hash_str[:16]


def generate_folder_name(old_url: str, new_url: str = None, url_hash: str = None) -> str:
    """
    Generate a readable folder name based on URLs.
    Args:
        old_url (str): Original URL
        new_url (str): New URL (optional)
        url_hash (str): Pre-computed URL hash (optional)
    Returns:
        str: Folder name
    """
    if not url_hash:
        url_hash = generate_url_hash(old_url, new_url)

    # Extract domain from old URL for readability
    try:
        parsed = urlparse(old_url)
        if parsed.scheme == "file":
            # For file URLs, use filename
            domain_part = Path(parsed.path).stem or "local_file"
        else:
            # For web URLs, use domain
            domain = parsed.hostname or "unknown"
            if domain.startswith("www."):
                domain = domain[4:]
            # Replace dots and special chars with underscores
            domain_part = re.sub(r"[^\w]", "_", domain)
    except Exception:
        domain_part = "unknown"

    # Combine domain and hash for uniqueness + readability
    folder_name = f"{domain_part}_{url_hash}"

    # Ensure it's a valid folder name and reasonable length
    folder_name = re.sub(r'[<>:"/\\|?*]', "_", folder_name)
    folder_name = folder_name[:50]  # Limit length

    return folder_name


class ProgressDatabase:
    """Thread-safe SQLite database for tracking URL comparison progress."""

    def __init__(self, output_folder: str):
        """Initialize database connection."""
        self.db_path = Path(output_folder) / "progress.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self):
        """Create database tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            # Check if old schema exists and migrate if needed
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='results'")
            table_exists = cursor.fetchone()

            if table_exists:
                # Check if it's the old schema (has row_number column)
                cursor = conn.execute("PRAGMA table_info(results)")
                columns = [col[1] for col in cursor.fetchall()]
                if "row_number" in columns and "url_hash" not in columns:
                    logger.info("Migrating from old row-based schema to URL-based schema...")
                    self._migrate_to_url_schema(conn)

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS csv_metadata (
                    id INTEGER PRIMARY KEY,
                    filename TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    row_count INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS results (
                    url_hash TEXT PRIMARY KEY,
                    old_url_original TEXT NOT NULL,
                    new_url_original TEXT,
                    old_url_normalized TEXT NOT NULL,
                    new_url_normalized TEXT,
                    title TEXT,
                    original_title TEXT,
                    subfolder_name TEXT,
                    old_screenshot_exists BOOLEAN DEFAULT FALSE,
                    new_screenshot_exists BOOLEAN DEFAULT FALSE,
                    diff_exists BOOLEAN DEFAULT FALSE,
                    metrics_json TEXT,
                    completed BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Create indexes for faster queries
            conn.execute("CREATE INDEX IF NOT EXISTS idx_results_completed ON results(completed)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_results_old_url ON results(old_url_original)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_results_new_url ON results(new_url_original)")

    def _migrate_to_url_schema(self, conn):
        """Migrate from old row-based schema to new URL-based schema."""
        try:
            # Create new table with URL-based schema
            conn.execute(
                """
                CREATE TABLE results_new (
                    url_hash TEXT PRIMARY KEY,
                    old_url_original TEXT NOT NULL,
                    new_url_original TEXT,
                    old_url_normalized TEXT NOT NULL,
                    new_url_normalized TEXT,
                    title TEXT,
                    original_title TEXT,
                    subfolder_name TEXT,
                    old_screenshot_exists BOOLEAN DEFAULT FALSE,
                    new_screenshot_exists BOOLEAN DEFAULT FALSE,
                    diff_exists BOOLEAN DEFAULT FALSE,
                    metrics_json TEXT,
                    completed BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Migrate existing data
            cursor = conn.execute("SELECT * FROM results")
            for row in cursor.fetchall():
                # Extract old schema data
                old_url = row[3]  # old_url column from old schema
                new_url = row[4]  # new_url column from old schema

                # Generate new schema data
                url_hash = generate_url_hash(old_url, new_url)
                old_url_normalized = normalize_url(old_url)
                new_url_normalized = normalize_url(new_url) if new_url else None
                subfolder_name = generate_folder_name(old_url, new_url, url_hash)

                # Insert into new table
                conn.execute(
                    """
                    INSERT OR REPLACE INTO results_new (
                        url_hash, old_url_original, new_url_original,
                        old_url_normalized, new_url_normalized,
                        title, original_title, subfolder_name,
                        old_screenshot_exists, new_screenshot_exists, diff_exists,
                        metrics_json, completed, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        url_hash,
                        old_url,
                        new_url,
                        old_url_normalized,
                        new_url_normalized,
                        row[1],
                        row[2],
                        subfolder_name,  # title, original_title
                        row[6],
                        row[7],
                        row[8],  # screenshot flags
                        row[9],
                        row[10],  # metrics_json, completed
                        row[11],
                        row[12],  # created_at, updated_at
                    ),
                )

            # Replace old table with new table
            conn.execute("DROP TABLE results")
            conn.execute("ALTER TABLE results_new RENAME TO results")

            logger.info("Successfully migrated to URL-based schema")

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            # Rollback by dropping new table if it exists
            conn.execute("DROP TABLE IF EXISTS results_new")
            raise

    def save_csv_metadata(self, csv_info: dict):
        """Save CSV file metadata for validation."""
        with sqlite3.connect(self.db_path) as conn:
            # Clear existing metadata and insert new
            conn.execute("DELETE FROM csv_metadata")
            conn.execute(
                """
                INSERT INTO csv_metadata (filename, size, row_count, content_hash)
                VALUES (?, ?, ?, ?)
            """,
                (csv_info["filename"], csv_info["size"], csv_info["row_count"], csv_info["content_hash"]),
            )

    def get_csv_metadata(self) -> dict:
        """Get stored CSV metadata."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT filename, size, row_count, content_hash
                FROM csv_metadata
                ORDER BY created_at DESC
                LIMIT 1
            """
            )
            row = cursor.fetchone()
            if row:
                return {"filename": row[0], "size": row[1], "row_count": row[2], "content_hash": row[3]}
            return {}

    def is_url_completed(self, old_url: str, new_url: str = None) -> bool:
        """Check if a specific URL combination has been completed."""
        url_hash = generate_url_hash(old_url, new_url)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT completed FROM results WHERE url_hash = ?", (url_hash,))
            row = cursor.fetchone()
            return bool(row and row[0])

    def get_completed_urls(self) -> set:
        """Get set of all completed URL hashes."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT url_hash FROM results WHERE completed = TRUE")
            return {row[0] for row in cursor.fetchall()}

    def get_url_hash_for_urls(self, old_url: str, new_url: str = None) -> str:
        """Get the URL hash for a given URL combination."""
        return generate_url_hash(old_url, new_url)

    def save_result(self, result: dict):
        """Save or update a comparison result."""
        with sqlite3.connect(self.db_path) as conn:
            # Generate URL-based identifiers
            old_url = result["old_url"]
            new_url = result.get("new_url")
            url_hash = generate_url_hash(old_url, new_url)
            old_url_normalized = normalize_url(old_url)
            new_url_normalized = normalize_url(new_url) if new_url else None

            # Use provided subfolder_name or generate one
            subfolder_name = result.get("subfolder_name")
            if not subfolder_name:
                subfolder_name = generate_folder_name(old_url, new_url, url_hash)

            # Serialize metrics to JSON
            metrics_json = json.dumps(result.get("metrics")) if result.get("metrics") else None

            conn.execute(
                """
                INSERT OR REPLACE INTO results (
                    url_hash, old_url_original, new_url_original,
                    old_url_normalized, new_url_normalized,
                    title, original_title, subfolder_name,
                    old_screenshot_exists, new_screenshot_exists, diff_exists,
                    metrics_json, completed, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
                (
                    url_hash,
                    old_url,
                    new_url,
                    old_url_normalized,
                    new_url_normalized,
                    result.get("title"),
                    result.get("original_title"),
                    subfolder_name,
                    result.get("old_screenshot_exists", False),
                    result.get("new_screenshot_exists", False),
                    result.get("diff_exists", False),
                    metrics_json,
                    True,  # Mark as completed when saving
                ),
            )

    def get_all_results(self) -> list:
        """Get all comparison results."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT url_hash, old_url_original, new_url_original, title, original_title,
                       subfolder_name, old_screenshot_exists, new_screenshot_exists,
                       diff_exists, metrics_json
                FROM results
                ORDER BY created_at
            """
            )

            results = []
            for row in cursor.fetchall():
                result = {
                    "url_hash": row[0],
                    "old_url": row[1],
                    "new_url": row[2],
                    "title": row[3],
                    "original_title": row[4],
                    "subfolder_name": row[5],
                    "old_screenshot_exists": bool(row[6]),
                    "new_screenshot_exists": bool(row[7]),
                    "diff_exists": bool(row[8]),
                    "metrics": json.loads(row[9]) if row[9] else None,
                }
                results.append(result)

            return results

    def get_progress_summary(self) -> dict:
        """Get summary of current progress."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT
                    COUNT(*) as total_urls,
                    COUNT(CASE WHEN completed = TRUE THEN 1 END) as completed_urls
                FROM results
            """
            )
            row = cursor.fetchone()

            return {
                "total_urls": row[0] or 0,
                "completed_urls": row[1] or 0,
                "completion_percentage": (row[1] / row[0] * 100) if row[0] > 0 else 0,
            }

    def clear_progress(self):
        """Clear all progress data (for fresh start with new CSV)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM results")
            conn.execute("DELETE FROM csv_metadata")
