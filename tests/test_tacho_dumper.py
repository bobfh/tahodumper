import pytest
import struct
from src.tacho_constants import (
    UNSIGNED_FIDS,
    CARD_TYPE_DRIVER,
    CARD_TYPE_WORKSHOP,
)
from src.ddd_builder import (
    build_ddd_binary,
    generate_ddd_filename,
    parse_card_identification,
    ORDERED_FIDS,
)

def test_unsigned_fids_contain_download_files():
    """Verify EF_Card_Download (0x050E, 0x0509) are in UNSIGNED_FIDS."""
    assert 0x050E in UNSIGNED_FIDS
    assert 0x0509 in UNSIGNED_FIDS
    assert 0x0002 in UNSIGNED_FIDS
    assert 0x0005 in UNSIGNED_FIDS
    assert 0xC100 in UNSIGNED_FIDS
    assert 0xC108 in UNSIGNED_FIDS

def test_workshop_card_no_signature_on_0509():
    """
    Ensure that build_ddd_binary never emits a signature block for 0x0509,
    even if passed in ef_signatures_map.
    """
    ef_data = {
        0x0002: b"\x00" * 25,
        0x0005: b"\x11" * 8,
        0x0501: b"\x02\x00\x00\x03\x06\x01\xec\x00\x08\x08\xff",  # Workshop card
        0xC100: b"\xcc" * 194,
        0xC108: b"\xca" * 194,
        0x0520: b"\x00" * 211,
        0x0509: b"\x00\x00",
        0x050A: b"\xaa" * 500,
        0x0502: b"\x02" * 100,
    }
    # Pretend a signature was mistakenly passed for 0x0509
    ef_sigs = {
        0x0501: b"\x51" * 128,
        0x0520: b"\x52" * 128,
        0x0509: b"\x59" * 128,  # Must be ignored!
        0x050A: b"\x5a" * 128,
        0x0502: b"\x52" * 128,
    }

    ddd_bytes = build_ddd_binary(ef_data, ef_sigs, generation=1)

    # Parse TLV blocks
    pos = 0
    blocks = []
    while pos + 5 <= len(ddd_bytes):
        fid, tag_type, length = struct.unpack(">HBH", ddd_bytes[pos:pos+5])
        pos += 5
        payload = ddd_bytes[pos:pos+length]
        pos += length
        blocks.append((fid, tag_type, length))

    # Verify no block has FID 0x0509 and tag_type 0x01
    sig_fids = [b[0] for b in blocks if b[1] == 0x01]
    assert 0x0509 not in sig_fids, "0x0509 (Card Download) must NEVER have a signature block!"

    # Verify order: 0x0509 data, then 0x050A data, then 0x050A sig, then 0x0502
    block_fids_tags = [(b[0], b[1]) for b in blocks]
    idx_0509 = block_fids_tags.index((0x0509, 0x00))
    idx_050a_data = block_fids_tags.index((0x050A, 0x00))
    idx_050a_sig = block_fids_tags.index((0x050A, 0x01))
    idx_0502_data = block_fids_tags.index((0x0502, 0x00))

    assert idx_0509 < idx_050a_data < idx_050a_sig < idx_0502_data, "Workshop EFs must be correctly ordered!"

def test_driver_card_filename_and_blocks():
    """Verify Driver Card file structure and prefix."""
    ef_data = {
        0x0002: b"\x00" * 25,
        0x0005: b"\x11" * 8,
        0x0501: b"\x01\x00\x00\x03\x06\x01\xec\x00\x08\x08\xff",  # Driver card (0x01)
        0x0520: b"\x01" + b"CARD123456789012" + b"\x01" + b"SMITH".ljust(35, b" ") + b"\x01" + b"JOHN".ljust(35, b" "),
        0x050E: b"\x00\x00\x00\x00",
    }
    fname = generate_ddd_filename(ef_data)
    assert fname.startswith("C_SMITH_CARD123456789012_")
