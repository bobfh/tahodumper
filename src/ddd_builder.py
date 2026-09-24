from __future__ import annotations

"""
DDD File Builder and Tachograph Data Encapsulation
Formats dumped EF data and digital signatures into standard tachograph .ddd binary file
according to EU Council Regulation (EEC) No 3821/85 / Regulation (EU) 2016/799 Appendix 7.
"""

import os
import struct
import datetime
from typing import Dict, Optional, Tuple, List
from .logger import logger
from .tacho_constants import UNSIGNED_FIDS

# Standard order of Elementary Files for Tachograph Cards (Annex 1B/1C Section 4 & Appendix 7)
# Note: For workshop cards, 0x0509, 0x050A, 0x050B are located immediately after 0x0520.
ORDERED_FIDS: List[int] = [
    0x0002,  # EF_ICC (Card identification - root MF)
    0x0005,  # EF_IC (Chip component info - root MF)
    0x0501,  # EF_Application_Identification
    0xC100,  # EF_Card_Certificate
    0xC108,  # EF_CA_Certificate
    0x0520,  # EF_Identification (Cardholder name & card number)
    0x050E,  # EF_Card_Download (Driver)
    0x0509,  # EF_Card_Download_Workshop (Calibration count)
    0x050A,  # EF_Calibration_Data (Workshop)
    0x050B,  # EF_Sensor_Installation_Data (Workshop)
    0x0521,  # EF_Driving_Licence_Info
    0x0502,  # EF_Events_Data
    0x0503,  # EF_Faults_Data
    0x0504,  # EF_Driver_Activity_Data
    0x0505,  # EF_Vehicles_Used
    0x0506,  # EF_Places
    0x0507,  # EF_Current_Usage
    0x0508,  # EF_Control_Activity_Data
    0x0522,  # EF_Specific_Conditions
]

def parse_card_identification(ef_0520_data: bytes) -> Dict[str, str]:
    """
    Extracts basic info from EF_Identification (FID 0x0520).
    Annex 1B CardIdentification structure:
    - cardIssuingMemberState: 1 byte (NationNumeric)
    - cardNumber: 16 bytes (CardNumber: 14 chars card sequence + 2 chars replacement/renewal)
    - cardHolderSurname: Name (36 bytes: code page 1 byte + 35 chars string)
    - cardHolderFirstNames: Name (36 bytes: code page 1 byte + 35 chars string)
    - cardHolderBirthDate: TimeReal (4 bytes)
    - cardHolderPreferredLanguage: 2 bytes ASCII
    """
    info = {
        "card_number": "",
        "holder_surname": "",
        "holder_name": "",
    }
    try:
        if len(ef_0520_data) >= 1 + 16:
            raw_card_num = ef_0520_data[1:17]
            card_num = raw_card_num.decode("ascii", errors="ignore").strip()
            card_num = "".join(c for c in card_num if c.isalnum() or c in "-_")
            info["card_number"] = card_num

        if len(ef_0520_data) >= 17 + 36:
            raw_surname = ef_0520_data[18:18+35]
            try:
                surname = raw_surname.decode("utf-8", errors="ignore").strip()
            except Exception:
                surname = raw_surname.decode("latin-1", errors="ignore").strip()
            info["holder_surname"] = "".join(c for c in surname if c.isalnum() or c in " -_")

        if len(ef_0520_data) >= 17 + 36 + 36:
            raw_fname = ef_0520_data[18+36:18+36+35]
            try:
                fname = raw_fname.decode("utf-8", errors="ignore").strip()
            except Exception:
                fname = raw_fname.decode("latin-1", errors="ignore").strip()
            info["holder_name"] = "".join(c for c in fname if c.isalnum() or c in " -_")
    except Exception as e:
        logger.warning(f"Could not parse EF_Identification metadata: {e}")

    return info

def get_card_type_prefix(ef_data_map: Dict[int, bytes]) -> str:
    """
    Determines standard file prefix based on CardType (Annex 1B EquipmentType):
    'C_' - Driver Card (CardType = 1)
    'W_' - Workshop Card (CardType = 2)
    'K_' - Control Card (CardType = 3)
    'S_' - Company Card (CardType = 4)
    """
    # 1. Try reading CardType from EF_Application_Identification (FID 0x0501)
    if 0x0501 in ef_data_map and len(ef_data_map[0x0501]) >= 1:
        card_type = ef_data_map[0x0501][0]
        if card_type == 2:
            return "W"
        elif card_type == 3:
            return "K"
        elif card_type == 4:
            return "S"
        elif card_type == 1:
            return "C"

    # 2. Heuristic: if workshop calibration data (0x050A / 0x0509) is present, it's a workshop card
    if 0x050A in ef_data_map or 0x0509 in ef_data_map:
        return "W"

    return "C"

def build_ddd_binary(
    ef_data_map: Dict[int, bytes],
    ef_signatures_map: Optional[Dict[int, bytes]] = None,
    generation: int = 1
) -> bytes:
    """
    Builds a standard tachograph .ddd binary file according to EU Annex 1B / 1C Appendix 7.
    Format is a succession of TLV records:
    [FID: 2 bytes big-endian] [Appendix / TagType: 1 byte] [Length: 2 bytes big-endian] [Value]
    TagType:
      0x00: Gen 1 Data
      0x01: Gen 1 Signature
      0x02: Gen 2 Data
      0x03: Gen 2 Signature
    """
    output = bytearray()
    if ef_signatures_map is None:
        ef_signatures_map = {}

    # Sequence: follow ordered standard list first, then any extra FIDs found
    all_fids = list(ORDERED_FIDS)
    for fid in ef_data_map.keys():
        if fid not in all_fids:
            all_fids.append(fid)

    for fid in all_fids:
        if fid not in ef_data_map:
            continue
        data = ef_data_map[fid]
        if not data:
            continue

        data_len = len(data)
        data_tag_type = 0x00 if generation == 1 else 0x02
        # 5-byte TLV header: [FID: 2B] [TagType: 1B] [Length: 2B]
        data_header = struct.pack(">HBH", fid, data_tag_type, data_len)
        output.extend(data_header)
        output.extend(data)
        logger.debug(f"DDD Block DATA: FID=0x{fid:04X}, TagType=0x{data_tag_type:02X}, Length={data_len} bytes")

        # If a digital signature exists for this EF and EF is signable, append signature block immediately
        if fid not in UNSIGNED_FIDS and fid in ef_signatures_map and ef_signatures_map[fid]:
            sig = ef_signatures_map[fid]
            sig_len = len(sig)
            sig_tag_type = 0x01 if generation == 1 else 0x03
            sig_header = struct.pack(">HBH", fid, sig_tag_type, sig_len)
            output.extend(sig_header)
            output.extend(sig)
            logger.debug(f"DDD Block SIGNATURE: FID=0x{fid:04X}, TagType=0x{sig_tag_type:02X}, Length={sig_len} bytes")

    return bytes(output)

def generate_ddd_filename(ef_data_map: Dict[int, bytes]) -> str:
    """
    Generates filename according to EU convention:
    <Prefix>_<CardHolder>_<CardNumber>_<Timestamp>.ddd
    Prefix: C_ (Driver), W_ (Workshop), K_ (Control), S_ (Company)
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = get_card_type_prefix(ef_data_map)
    card_info = {}
    
    if 0x0520 in ef_data_map:
        card_info = parse_card_identification(ef_data_map[0x0520])

    card_num = card_info.get("card_number")
    surname = card_info.get("holder_surname")

    if card_num and surname:
        return f"{prefix}_{surname}_{card_num}_{timestamp}.ddd"
    elif card_num:
        return f"{prefix}_{card_num}_{timestamp}.ddd"
    elif surname:
        return f"{prefix}_{surname}_{timestamp}.ddd"
    else:
        return f"{prefix}_dump_{timestamp}.ddd"

def save_ddd_file(
    ef_data_map: Dict[int, bytes],
    output_dir: str,
    ef_signatures_map: Optional[Dict[int, bytes]] = None,
    generation: int = 1
) -> Tuple[str, int]:
    """
    Packages EFs into DDD and writes file to output_dir.
    Returns (full_file_path, bytes_written).
    """
    os.makedirs(output_dir, exist_ok=True)
    filename = generate_ddd_filename(ef_data_map)
    file_path = os.path.join(output_dir, filename)

    ddd_bytes = build_ddd_binary(ef_data_map, ef_signatures_map=ef_signatures_map, generation=generation)
    
    with open(file_path, "wb") as f:
        f.write(ddd_bytes)

    logger.info(f"Saved DDD dump file: {file_path} ({len(ddd_bytes)} bytes)")
    return file_path, len(ddd_bytes)
