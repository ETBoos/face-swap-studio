"""Local one-time trial codes.

Map each code to a duration in days (1 or 30). To add a code, insert one
line in CODE_TABLE. See docs/ACTIVATION_CODES.md.

Used/unused state is not stored here. LicenseStore writes it to license.json.
These codes are not signed. Editing the local license file can bypass the check.
"""

from __future__ import annotations

# code -> duration days. FS-1D = 1 day trial, FS-30D = 30 day trial.
CODE_TABLE: dict[str, int] = {
    "FS-1D-MWYT-CDUW-ESHY": 1,
    "FS-1D-VBQQ-SDRG-VFF8": 1,
    "FS-1D-HD2F-DXWH-68PF": 1,
    "FS-1D-WAS2-7WQ5-C7J7": 1,
    "FS-1D-YUPL-56UW-93V7": 1,
    "FS-1D-MSB2-9KXJ-2TL5": 1,
    "FS-1D-8QEB-S2R2-B2Y6": 1,
    "FS-1D-N8XU-JPAF-YNS8": 1,
    "FS-1D-VATX-Y5LC-8MU3": 1,
    "FS-1D-8QK3-5ZNT-BRQS": 1,
    "FS-1D-DFY6-AHBG-ACLQ": 1,
    "FS-1D-CNHP-QC77-KPKP": 1,
    "FS-1D-2YDC-9V8H-HDQK": 1,
    "FS-1D-S8QG-F3FT-WQE4": 1,
    "FS-1D-P2Y6-RMU6-AS73": 1,
    "FS-1D-RZP8-EUX6-RXY5": 1,
    "FS-1D-TQU8-N9LH-542H": 1,
    "FS-1D-P6EQ-762V-NNDW": 1,
    "FS-1D-N3BH-GZUV-FD2R": 1,
    "FS-1D-WMSX-BHVU-YJ6L": 1,
    "FS-30D-E4F2-8A7Z-ARSJ": 30,
    "FS-30D-N3SK-YX6X-YZSE": 30,
    "FS-30D-U6X9-FFVN-QNBJ": 30,
    "FS-30D-SR8T-PDCB-ZMHH": 30,
    "FS-30D-MT8D-7Z5X-5FDE": 30,
    "FS-30D-CFZ5-AWJG-2ZEF": 30,
    "FS-30D-7UML-D9N5-CTQ3": 30,
    "FS-30D-3DWV-6BE8-N978": 30,
    "FS-30D-AUFA-88WT-2Y8X": 30,
    "FS-30D-VV7Z-QAX3-9DAP": 30,
    "FS-30D-3U3F-2X6E-ZVF9": 30,
    "FS-30D-C4S2-WZZK-MMPU": 30,
    "FS-30D-4FR9-ZV8H-GV5G": 30,
    "FS-30D-S53H-4BZS-RE5V": 30,
    "FS-30D-D7W3-C5RS-QSSR": 30,
    "FS-30D-QDXV-PT8M-7MUU": 30,
    "FS-30D-M3KW-ZF8K-L6AS": 30,
    "FS-30D-J5QY-D9HX-8ZS2": 30,
    "FS-30D-NSWU-VVZ9-3MCS": 30,
    "FS-30D-3FZY-CB9P-GARX": 30,
}


def normalize_code(code: str) -> str:
    return "".join(str(code).split()).upper()


def duration_days(code: str) -> int | None:
    """Return 1 or 30 when the code is in the table, otherwise None."""
    days = CODE_TABLE.get(normalize_code(code))
    if days not in (1, 30):
        return None
    return days
