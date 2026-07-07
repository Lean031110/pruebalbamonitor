"""Tests de utilidades WMI (identificación compuesta de USBs)."""
from __future__ import annotations

from lbamonitor.monitor.wmi_utils import (
    USBDeviceInfo,
    compute_fingerprint,
    is_windows,
    list_removable_drives,
    normalize_serial,
    parse_vid_pid,
)


class TestComputeFingerprint:
    def test_both_present(self) -> None:
        fp = compute_fingerprint("\\\\.\\PHYSICALDRIVE2", "A1B2-C3D4")
        # SHA-256 hex de 64 chars
        assert len(fp) == 64
        assert all(c in "0123456789abcdef" for c in fp)

    def test_deterministic(self) -> None:
        """Mismos inputs → mismo fingerprint."""
        fp1 = compute_fingerprint("DRIVE1", "SERIAL1")
        fp2 = compute_fingerprint("DRIVE1", "SERIAL1")
        assert fp1 == fp2

    def test_case_insensitive(self) -> None:
        """Mayúsculas/minúsculas no afectan el fingerprint."""
        fp1 = compute_fingerprint("DRIVE1", "SERIAL1")
        fp2 = compute_fingerprint("drive1", "serial1")
        assert fp1 == fp2

    def test_different_inputs_different_fp(self) -> None:
        fp1 = compute_fingerprint("DRIVE1", "SERIAL1")
        fp2 = compute_fingerprint("DRIVE2", "SERIAL2")
        assert fp1 != fp2

    def test_empty_inputs(self) -> None:
        assert compute_fingerprint("", "") == ""
        assert compute_fingerprint(None, None) == ""

    def test_one_empty(self) -> None:
        """Si solo uno está vacío, usa el otro."""
        fp1 = compute_fingerprint("DRIVE1", "")
        fp2 = compute_fingerprint("", "SERIAL1")
        assert fp1 != ""
        assert fp2 != ""
        assert fp1 != fp2


class TestParseVidPid:
    def test_standard_pnp_id(self) -> None:
        pnp = "USB\\VID_0951&PID_1666\\AA0000000001"
        vid, pid = parse_vid_pid(pnp)
        assert vid == "0951"
        assert pid == "1666"

    def test_case_insensitive(self) -> None:
        pnp = "USB\\vid_0951&pid_1666\\AA0000000001"
        vid, pid = parse_vid_pid(pnp)
        assert vid == "0951"
        assert pid == "1666"

    def test_no_vid_pid(self) -> None:
        vid, pid = parse_vid_pid("USB\\SIN_IDENTIFICAR")
        assert vid == ""
        assert pid == ""

    def test_empty(self) -> None:
        vid, pid = parse_vid_pid("")
        assert vid == ""
        assert pid == ""


class TestNormalizeSerial:
    def test_normal_serial(self) -> None:
        assert normalize_serial("AA11BB22CC33") == "AA11BB22CC33"

    def test_null_values(self) -> None:
        assert normalize_serial("NULL") == ""
        assert normalize_serial("null") == ""
        assert normalize_serial("None") == ""
        assert normalize_serial("0") == ""

    def test_whitespace(self) -> None:
        assert normalize_serial("  AA11BB22  ") == "AA11BB22"
        assert normalize_serial("   ") == ""

    def test_empty(self) -> None:
        assert normalize_serial("") == ""
        assert normalize_serial(None) == ""


class TestUSBDeviceInfo:
    def test_fingerprint_auto_computed(self) -> None:
        info = USBDeviceInfo(
            drive_letter="E:",
            device_id="\\\\.\\PHYSICALDRIVE2",
            volume_serial="A1B2-C3D4",
        )
        assert info.fingerprint != ""
        assert len(info.fingerprint) == 64

    def test_fingerprint_empty_when_no_ids(self) -> None:
        info = USBDeviceInfo(drive_letter="E:")
        assert info.fingerprint == ""

    def test_fingerprint_consistent_with_compute(self) -> None:
        info = USBDeviceInfo(
            drive_letter="E:",
            device_id="DRIVE1",
            volume_serial="SERIAL1",
        )
        expected = compute_fingerprint("DRIVE1", "SERIAL1")
        assert info.fingerprint == expected


class TestPlatformGuards:
    def test_is_windows(self) -> None:
        """En Linux/Mac devuelve False, en Windows True."""
        import os
        assert is_windows() == (os.name == "nt")

    def test_list_removable_drives_no_crash(self) -> None:
        """list_removable_drives no debe crashear en ninguna plataforma."""
        drives = list_removable_drives()
        assert isinstance(drives, list)
        # En Linux del test, probablemente devuelve paths de /media
