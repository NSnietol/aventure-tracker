"""File organizer service for calendar images.

Detects real file types, renames files with correct extensions,
and organizes them into agency/year/month structure.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path

# Magic bytes for common image formats
MAGIC_BYTES = {
    b"\xff\xd8\xff": "jpg",  # JPEG
    b"\x89PNG\r\n\x1a\n": "png",  # PNG
    b"GIF87a": "gif",  # GIF87a
    b"GIF89a": "gif",  # GIF89a
    b"RIFF": "webp",  # WebP (starts with RIFF, need to check further)
}

# Month name mappings (Spanish)
MONTH_NAMES = {
    "enero": "01",
    "febrero": "02",
    "marzo": "03",
    "abril": "04",
    "mayo": "05",
    "junio": "06",
    "julio": "07",
    "agosto": "08",
    "septiembre": "09",
    "octubre": "10",
    "noviembre": "11",
    "diciembre": "12",
}

# Agency name normalization
AGENCY_ALIASES = {
    "brutal": "brutaltravel",
    "brutaltravel": "brutaltravel",
    "brutal-travel": "brutaltravel",
    "medellin-bunge": "medellinbungee",
    "medellinbungee": "medellinbungee",
    "medellin-bungee": "medellinbungee",
    "bungee": "medellinbungee",
}


@dataclass
class OrganizedFile:
    """Result of organizing a single file."""

    original_path: Path
    new_path: Path
    detected_type: str
    agency: str
    year: int
    month: str
    success: bool
    error: str | None = None


@dataclass
class OrganizationResult:
    """Result of organizing a directory of files."""

    source_dir: Path
    target_dir: Path
    files: list[OrganizedFile]
    total_processed: int
    total_success: int
    total_failed: int


def detect_file_type(file_path: Path) -> str | None:
    """Detect real file type using magic bytes.

    Args:
        file_path: Path to the file to analyze.

    Returns:
        File extension (without dot) if detected, None otherwise.
    """
    try:
        with open(file_path, "rb") as f:
            header = f.read(12)  # Read enough bytes for detection

        # Check JPEG (most common for WhatsApp)
        if header[:3] == b"\xff\xd8\xff":
            return "jpg"

        # Check PNG
        if header[:8] == b"\x89PNG\r\n\x1a\n":
            return "png"

        # Check GIF
        if header[:6] in (b"GIF87a", b"GIF89a"):
            return "gif"

        # Check WebP (RIFF....WEBP)
        if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
            return "webp"

        return None
    except OSError:
        return None


def normalize_agency_name(name: str) -> str:
    """Normalize agency folder name to standard format.

    Args:
        name: Raw agency folder name.

    Returns:
        Normalized agency name.
    """
    normalized = name.lower().strip()
    return AGENCY_ALIASES.get(normalized, normalized)


def get_month_number(month_name: str) -> str | None:
    """Convert month name to number.

    Args:
        month_name: Month name in Spanish.

    Returns:
        Two-digit month number or None if not recognized.
    """
    return MONTH_NAMES.get(month_name.lower().strip())


class FileOrganizer:
    """Organizes calendar images into structured directories."""

    def __init__(self, target_base_dir: Path, year: int = 2026):
        """Initialize the file organizer.

        Args:
            target_base_dir: Base directory for organized files (e.g., data/agencies).
            year: Default year for events (default: 2026).
        """
        self.target_base_dir = Path(target_base_dir)
        self.year = year

    def organize_directory(
        self,
        source_dir: Path,
        month: str = "agosto",
    ) -> OrganizationResult:
        """Organize all image files from source directory.

        Args:
            source_dir: Directory containing raw calendar images organized by agency.
            month: Target month for the files (default: agosto).

        Returns:
            OrganizationResult with details of all processed files.
        """
        source_dir = Path(source_dir)
        organized_files: list[OrganizedFile] = []

        # Find all agency subdirectories
        if not source_dir.exists():
            return OrganizationResult(
                source_dir=source_dir,
                target_dir=self.target_base_dir,
                files=[],
                total_processed=0,
                total_success=0,
                total_failed=0,
            )

        for agency_dir in source_dir.iterdir():
            if not agency_dir.is_dir() or agency_dir.name.startswith("."):
                continue

            agency_name = normalize_agency_name(agency_dir.name)
            month_num = get_month_number(month) or month

            # Process each file in agency directory
            for file_path in agency_dir.iterdir():
                if file_path.name.startswith("."):
                    continue

                result = self._organize_file(
                    file_path=file_path,
                    agency=agency_name,
                    month=month,
                    month_num=month_num,
                )
                organized_files.append(result)

        total_success = sum(1 for f in organized_files if f.success)
        total_failed = len(organized_files) - total_success

        return OrganizationResult(
            source_dir=source_dir,
            target_dir=self.target_base_dir,
            files=organized_files,
            total_processed=len(organized_files),
            total_success=total_success,
            total_failed=total_failed,
        )

    def _organize_file(
        self,
        file_path: Path,
        agency: str,
        month: str,
        month_num: str,
    ) -> OrganizedFile:
        """Organize a single file.

        Args:
            file_path: Path to the source file.
            agency: Normalized agency name.
            month: Month name.
            month_num: Month number (01-12).

        Returns:
            OrganizedFile with result details.
        """
        # Detect real file type
        detected_type = detect_file_type(file_path)

        if detected_type is None:
            return OrganizedFile(
                original_path=file_path,
                new_path=file_path,
                detected_type="unknown",
                agency=agency,
                year=self.year,
                month=month,
                success=False,
                error=f"Could not detect file type for {file_path.name}",
            )

        # Create target directory
        target_dir = self.target_base_dir / agency / str(self.year) / month
        target_dir.mkdir(parents=True, exist_ok=True)

        # Generate new filename with correct extension
        # Use original stem but with correct extension
        stem = file_path.stem
        new_filename = f"{stem}.{detected_type}"
        new_path = target_dir / new_filename

        # Handle filename collisions
        counter = 1
        while new_path.exists():
            new_filename = f"{stem}_{counter}.{detected_type}"
            new_path = target_dir / new_filename
            counter += 1

        try:
            # Copy file to new location
            shutil.copy2(file_path, new_path)

            return OrganizedFile(
                original_path=file_path,
                new_path=new_path,
                detected_type=detected_type,
                agency=agency,
                year=self.year,
                month=month,
                success=True,
            )
        except OSError as e:
            return OrganizedFile(
                original_path=file_path,
                new_path=new_path,
                detected_type=detected_type,
                agency=agency,
                year=self.year,
                month=month,
                success=False,
                error=str(e),
            )

    def list_organized_files(self, agency: str | None = None) -> list[Path]:
        """List all organized image files.

        Args:
            agency: Filter by agency name (optional).

        Returns:
            List of paths to organized image files.
        """
        image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
        files: list[Path] = []

        search_dir = self.target_base_dir
        if agency:
            search_dir = search_dir / normalize_agency_name(agency)

        if not search_dir.exists():
            return files

        for path in search_dir.rglob("*"):
            if path.is_file() and path.suffix.lower() in image_extensions:
                files.append(path)

        return sorted(files)
