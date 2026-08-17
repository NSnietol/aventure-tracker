"""Tests for file organizer service."""

from pathlib import Path

import pytest

from aventure_tracker.services.file_organizer import (
    FileOrganizer,
    detect_file_type,
    get_month_number,
    normalize_agency_name,
)


class TestDetectFileType:
    """Tests for file type detection."""

    def test_detect_jpeg(self, tmp_path: Path) -> None:
        """Should detect JPEG files by magic bytes."""
        jpeg_file = tmp_path / "test.txt"
        # JPEG magic bytes
        jpeg_file.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF")

        assert detect_file_type(jpeg_file) == "jpg"

    def test_detect_png(self, tmp_path: Path) -> None:
        """Should detect PNG files by magic bytes."""
        png_file = tmp_path / "test.txt"
        # PNG magic bytes
        png_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0d")

        assert detect_file_type(png_file) == "png"

    def test_detect_gif87a(self, tmp_path: Path) -> None:
        """Should detect GIF87a files."""
        gif_file = tmp_path / "test.bin"
        gif_file.write_bytes(b"GIF87a\x00\x00\x00\x00\x00\x00")

        assert detect_file_type(gif_file) == "gif"

    def test_detect_gif89a(self, tmp_path: Path) -> None:
        """Should detect GIF89a files."""
        gif_file = tmp_path / "test.bin"
        gif_file.write_bytes(b"GIF89a\x00\x00\x00\x00\x00\x00")

        assert detect_file_type(gif_file) == "gif"

    def test_detect_webp(self, tmp_path: Path) -> None:
        """Should detect WebP files."""
        webp_file = tmp_path / "test.txt"
        # WebP magic bytes: RIFF....WEBP
        webp_file.write_bytes(b"RIFF\x00\x00\x00\x00WEBP")

        assert detect_file_type(webp_file) == "webp"

    def test_detect_unknown(self, tmp_path: Path) -> None:
        """Should return None for unknown file types."""
        unknown_file = tmp_path / "test.txt"
        unknown_file.write_bytes(b"Hello, this is just text")

        assert detect_file_type(unknown_file) is None

    def test_detect_nonexistent_file(self, tmp_path: Path) -> None:
        """Should return None for nonexistent files."""
        fake_file = tmp_path / "does_not_exist.jpg"

        assert detect_file_type(fake_file) is None

    def test_detect_empty_file(self, tmp_path: Path) -> None:
        """Should return None for empty files."""
        empty_file = tmp_path / "empty.txt"
        empty_file.write_bytes(b"")

        assert detect_file_type(empty_file) is None


class TestNormalizeAgencyName:
    """Tests for agency name normalization."""

    def test_brutal_variations(self) -> None:
        """Should normalize all brutal variations to brutaltravel."""
        assert normalize_agency_name("brutal") == "brutaltravel"
        assert normalize_agency_name("brutaltravel") == "brutaltravel"
        assert normalize_agency_name("brutal-travel") == "brutaltravel"
        assert normalize_agency_name("BRUTAL") == "brutaltravel"
        assert normalize_agency_name("  brutal  ") == "brutaltravel"

    def test_medellin_bungee_variations(self) -> None:
        """Should normalize all medellin bungee variations."""
        assert normalize_agency_name("medellin-bunge") == "medellinbungee"
        assert normalize_agency_name("medellinbungee") == "medellinbungee"
        assert normalize_agency_name("medellin-bungee") == "medellinbungee"
        assert normalize_agency_name("bungee") == "medellinbungee"

    def test_unknown_agency(self) -> None:
        """Should return lowercase name for unknown agencies."""
        assert normalize_agency_name("newagency") == "newagency"
        assert normalize_agency_name("NEW-AGENCY") == "new-agency"


class TestGetMonthNumber:
    """Tests for month name to number conversion."""

    def test_all_months(self) -> None:
        """Should convert all Spanish month names to numbers."""
        assert get_month_number("enero") == "01"
        assert get_month_number("febrero") == "02"
        assert get_month_number("marzo") == "03"
        assert get_month_number("abril") == "04"
        assert get_month_number("mayo") == "05"
        assert get_month_number("junio") == "06"
        assert get_month_number("julio") == "07"
        assert get_month_number("agosto") == "08"
        assert get_month_number("septiembre") == "09"
        assert get_month_number("octubre") == "10"
        assert get_month_number("noviembre") == "11"
        assert get_month_number("diciembre") == "12"

    def test_case_insensitive(self) -> None:
        """Should handle different cases."""
        assert get_month_number("AGOSTO") == "08"
        assert get_month_number("Agosto") == "08"
        assert get_month_number("  agosto  ") == "08"

    def test_invalid_month(self) -> None:
        """Should return None for invalid month names."""
        assert get_month_number("invalid") is None
        assert get_month_number("august") is None  # English


class TestFileOrganizer:
    """Tests for FileOrganizer class."""

    @pytest.fixture
    def organizer(self, tmp_path: Path) -> FileOrganizer:
        """Create a FileOrganizer instance."""
        target_dir = tmp_path / "data" / "agencies"
        return FileOrganizer(target_dir, year=2026)

    @pytest.fixture
    def source_with_images(self, tmp_path: Path) -> Path:
        """Create a source directory with test images."""
        source_dir = tmp_path / "agent-calendars"

        # Create brutal agency folder with JPEG files (disguised as .txt)
        brutal_dir = source_dir / "brutal"
        brutal_dir.mkdir(parents=True)
        (brutal_dir / "calendar1.txt").write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF")
        (brutal_dir / "calendar2.txt").write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF")

        # Create medellin-bunge folder with PNG file
        medellin_dir = source_dir / "medellin-bunge"
        medellin_dir.mkdir(parents=True)
        (medellin_dir / "events.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0d")

        return source_dir

    def test_organize_directory(
        self, organizer: FileOrganizer, source_with_images: Path
    ) -> None:
        """Should organize files into correct structure."""
        result = organizer.organize_directory(source_with_images, month="agosto")

        assert result.total_processed == 3
        assert result.total_success == 3
        assert result.total_failed == 0

        # Check files were created in correct locations
        brutal_dir = organizer.target_base_dir / "brutaltravel" / "2026" / "agosto"
        assert brutal_dir.exists()
        assert (brutal_dir / "calendar1.jpg").exists()
        assert (brutal_dir / "calendar2.jpg").exists()

        medellin_dir = organizer.target_base_dir / "medellinbungee" / "2026" / "agosto"
        assert medellin_dir.exists()
        assert (medellin_dir / "events.png").exists()

    def test_organize_detects_correct_types(
        self, organizer: FileOrganizer, source_with_images: Path
    ) -> None:
        """Should detect correct file types regardless of extension."""
        result = organizer.organize_directory(source_with_images, month="agosto")

        # Find the brutal files
        brutal_files = [f for f in result.files if f.agency == "brutaltravel"]
        assert len(brutal_files) == 2
        assert all(f.detected_type == "jpg" for f in brutal_files)

        # Find the medellin file
        medellin_files = [f for f in result.files if f.agency == "medellinbungee"]
        assert len(medellin_files) == 1
        assert medellin_files[0].detected_type == "png"

    def test_organize_handles_unknown_types(
        self, organizer: FileOrganizer, tmp_path: Path
    ) -> None:
        """Should handle files with unknown types gracefully."""
        source_dir = tmp_path / "source"
        agency_dir = source_dir / "brutal"
        agency_dir.mkdir(parents=True)
        (agency_dir / "document.pdf").write_bytes(b"%PDF-1.4 fake pdf content")

        result = organizer.organize_directory(source_dir, month="agosto")

        assert result.total_processed == 1
        assert result.total_failed == 1
        assert result.files[0].error is not None
        assert "Could not detect file type" in result.files[0].error

    def test_organize_empty_directory(
        self, organizer: FileOrganizer, tmp_path: Path
    ) -> None:
        """Should handle empty source directory."""
        source_dir = tmp_path / "empty"
        source_dir.mkdir()

        result = organizer.organize_directory(source_dir, month="agosto")

        assert result.total_processed == 0
        assert result.total_success == 0
        assert result.total_failed == 0

    def test_organize_nonexistent_directory(self, organizer: FileOrganizer) -> None:
        """Should handle nonexistent source directory."""
        result = organizer.organize_directory(Path("/does/not/exist"), month="agosto")

        assert result.total_processed == 0

    def test_organize_handles_filename_collision(
        self, organizer: FileOrganizer, tmp_path: Path
    ) -> None:
        """Should handle filename collisions by adding counter."""
        source_dir = tmp_path / "source"
        agency_dir = source_dir / "brutal"
        agency_dir.mkdir(parents=True)

        # Create two files with same stem
        (agency_dir / "calendar.txt").write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF")

        # First organize
        organizer.organize_directory(source_dir, month="agosto")

        # Create another file with same stem and organize again
        (agency_dir / "calendar.bin").write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF")
        organizer.organize_directory(source_dir, month="agosto")

        target_dir = organizer.target_base_dir / "brutaltravel" / "2026" / "agosto"
        files = list(target_dir.glob("calendar*.jpg"))
        assert len(files) >= 2

    def test_list_organized_files(
        self, organizer: FileOrganizer, source_with_images: Path
    ) -> None:
        """Should list all organized image files."""
        organizer.organize_directory(source_with_images, month="agosto")

        all_files = organizer.list_organized_files()
        assert len(all_files) == 3

        brutal_files = organizer.list_organized_files(agency="brutal")
        assert len(brutal_files) == 2

        medellin_files = organizer.list_organized_files(agency="medellin-bunge")
        assert len(medellin_files) == 1

    def test_list_organized_files_empty(self, organizer: FileOrganizer) -> None:
        """Should return empty list when no files organized."""
        files = organizer.list_organized_files()
        assert files == []

    def test_skips_hidden_files(self, organizer: FileOrganizer, tmp_path: Path) -> None:
        """Should skip hidden files like .DS_Store."""
        source_dir = tmp_path / "source"
        agency_dir = source_dir / "brutal"
        agency_dir.mkdir(parents=True)
        (agency_dir / ".DS_Store").write_bytes(b"mac stuff")
        (agency_dir / "calendar.txt").write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF")

        result = organizer.organize_directory(source_dir, month="agosto")

        assert result.total_processed == 1  # Only the calendar, not .DS_Store

    def test_skips_hidden_directories(
        self, organizer: FileOrganizer, tmp_path: Path
    ) -> None:
        """Should skip hidden directories."""
        source_dir = tmp_path / "source"
        hidden_dir = source_dir / ".hidden"
        hidden_dir.mkdir(parents=True)
        (hidden_dir / "file.jpg").write_bytes(b"\xff\xd8\xff\xe0")

        result = organizer.organize_directory(source_dir, month="agosto")

        assert result.total_processed == 0
