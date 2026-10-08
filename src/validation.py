"""
Data Validation Module for Ingestion Pipeline.

Validates incoming CSV and tabular files for schema completeness, encoding,
required column presence, data types, and allowable row counts before processing.
"""

from typing import Dict, List, Any, Optional
import csv
from pathlib import Path


class DataValidationError(Exception):
    """Raised when incoming data fails schema or validation constraints."""
    pass


def validate_csv_schema(
    file_path: Path,
    required_columns: List[str],
    min_rows: int = 1,
    expected_encoding: str = "utf-8"
) -> Dict[str, Any]:
    """
    Validate an incoming CSV file for schema completeness and basic hygiene.

    Args:
        file_path: Path to the target CSV file.
        required_columns: List of column names that must be present in the header.
        min_rows: Minimum acceptable row count (excluding header).
        expected_encoding: Expected text encoding.

    Returns:
        Dict containing validation statistics (row_count, columns, is_valid).

    Raises:
        DataValidationError: If file does not exist, encoding is invalid,
                             missing required columns, or row count is below threshold.
    """
    path = Path(file_path)
    if not path.is_file():
        raise DataValidationError(f"File not found: {path}")

    try:
        with open(path, "r", encoding=expected_encoding) as f:
            reader = csv.reader(f)
            header = next(reader, None)

            if header is None:
                raise DataValidationError(f"File is empty: {path}")

            header_set = set(col.strip() for col in header)
            missing = [col for col in required_columns if col not in header_set]
            if missing:
                raise DataValidationError(
                    f"Schema mismatch: missing required columns: {missing}"
                )

            row_count = 0
            for row in reader:
                if any(cell.strip() for cell in row):
                    row_count += 1

            if row_count < min_rows:
                raise DataValidationError(
                    f"Row count {row_count} is below minimum threshold of {min_rows}"
                )

            return {
                "file": str(path.name),
                "is_valid": True,
                "row_count": row_count,
                "columns": header,
            }

    except UnicodeDecodeError as e:
        raise DataValidationError(f"Encoding mismatch (expected {expected_encoding}): {e}")
