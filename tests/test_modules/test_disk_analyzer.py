"""Tests pour modules/disk_analyzer.py."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from winboost.core.base_module import RiskLevel, ScanResult, Issue
from winboost.modules.disk_analyzer import (
    DiskAnalyzer,
    _format_size,
    _dir_size_fast,
    _find_big_files,
    DISK_WARNING_PERCENT,
)


# --- Tests helpers ---

class TestFormatSize:
    def test_bytes(self):
        assert _format_size(0) == "0.0 o"

    def test_megabytes(self):
        assert "Mo" in _format_size(5 * 1024 * 1024)

    def test_gigabytes(self):
        assert "Go" in _format_size(3 * 1024**3)


class TestDirSizeFast:
    def test_empty_dir(self, tmp_path):
        assert _dir_size_fast(tmp_path) == 0

    def test_dir_with_files(self, tmp_path):
        (tmp_path / "a.txt").write_text("x" * 100)
        (tmp_path / "b.txt").write_text("y" * 200)
        size = _dir_size_fast(tmp_path)
        assert size >= 300

    def test_nested_dir(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "file.txt").write_text("data" * 50)
        size = _dir_size_fast(tmp_path, max_depth=2)
        assert size > 0

    def test_nonexistent_dir(self):
        assert _dir_size_fast(Path("/nonexistent/path")) == 0


class TestFindBigFiles:
    def test_finds_big_files(self, tmp_path):
        # Cree un fichier de 2 Mo
        big = tmp_path / "big.bin"
        big.write_bytes(b"\x00" * (2 * 1024 * 1024))
        # Et un petit
        small = tmp_path / "small.txt"
        small.write_text("hello")

        results = _find_big_files(tmp_path, threshold_bytes=1024 * 1024, max_results=10)
        assert len(results) == 1
        assert "big.bin" in results[0]["path"]

    def test_respects_max_results(self, tmp_path):
        for i in range(5):
            (tmp_path / f"file{i}.bin").write_bytes(b"\x00" * (2 * 1024 * 1024))

        results = _find_big_files(tmp_path, threshold_bytes=1024 * 1024, max_results=3)
        assert len(results) <= 3

    def test_empty_dir(self, tmp_path):
        results = _find_big_files(tmp_path, threshold_bytes=100, max_results=10)
        assert results == []


# --- Tests Properties ---

class TestDiskAnalyzerProperties:
    def test_name(self):
        assert DiskAnalyzer().name == "disk_analyzer"

    def test_risk_level(self):
        assert DiskAnalyzer().risk_level == RiskLevel.LOW


# --- Tests Scan ---

class TestDiskAnalyzerScan:
    def test_scan_returns_result(self):
        """Scan retourne un resultat valide."""
        result = DiskAnalyzer().scan()
        assert result.module_name == "disk_analyzer"
        assert "total_reclaimable" in result.metadata

    def test_scan_detects_low_disk(self):
        """Scan detecte un disque presque plein."""
        mock_partitions = [MagicMock(device="C:\\", mountpoint="C:\\")]
        mock_usage = MagicMock(percent=92, free=10 * 1024**3, total=128 * 1024**3)

        with (
            patch("winboost.modules.disk_analyzer.psutil.disk_partitions", return_value=mock_partitions),
            patch("winboost.modules.disk_analyzer.psutil.disk_usage", return_value=mock_usage),
        ):
            result = DiskAnalyzer().scan()

        disk_issues = [i for i in result.issues if i.id.startswith("disk_low_")]
        assert len(disk_issues) >= 1
        assert "92%" in disk_issues[0].description


# --- Tests Fix ---

class TestDiskAnalyzerFix:
    def test_fix_cleans_reclaimable(self, tmp_path):
        """Fix nettoie les dossiers reclaimables."""
        # Cree des fichiers dans le dossier
        (tmp_path / "cache1.tmp").write_text("data" * 100)
        (tmp_path / "cache2.tmp").write_text("data" * 100)

        scan_result = ScanResult(
            module_name="disk_analyzer",
            issues=[
                Issue(
                    id="disk_reclaimable_test",
                    description="Test cache",
                    metadata={
                        "path": str(tmp_path),
                        "size": 800,
                        "label": "Test cache",
                        "category": "reclaimable",
                    },
                ),
            ],
        )
        fix = DiskAnalyzer().fix(scan_result)
        assert fix.fixed_count == 1
        assert "liberes" in fix.fixed[0]

    def test_fix_skips_big_files(self):
        """Fix ne supprime pas les gros fichiers utilisateur."""
        scan_result = ScanResult(
            module_name="disk_analyzer",
            issues=[
                Issue(
                    id="disk_bigfile_test",
                    description="Gros fichier",
                    metadata={
                        "path": r"C:\Users\test\file.iso",
                        "size": 5 * 1024**3,
                        "category": "big_file",
                    },
                ),
            ],
        )
        fix = DiskAnalyzer().fix(scan_result)
        assert fix.fixed_count == 0
        assert len(fix.skipped) == 1
        assert "manuelle" in fix.skipped[0]

    def test_fix_skips_missing_folder(self):
        """Fix gere les dossiers qui n'existent plus."""
        scan_result = ScanResult(
            module_name="disk_analyzer",
            issues=[
                Issue(
                    id="disk_reclaimable_gone",
                    description="Gone",
                    metadata={
                        "path": r"C:\nonexistent\folder",
                        "size": 100,
                        "label": "Gone",
                        "category": "reclaimable",
                    },
                ),
            ],
        )
        fix = DiskAnalyzer().fix(scan_result)
        assert fix.fixed_count == 0
        assert len(fix.skipped) == 1
