from __future__ import annotations

"""
DDD File Parser and Decoder
Extracts and parses Elementary Files (EF) from tachograph .DDD binary files
Supports both Driver Cards (Annex 1B) and Workshop Cards (Annex 1B/1C).
"""

import struct
import datetime
from typing import Dict, List, Optional, Any

NATION_CODES = {
    0x00: "Не указано",
    0x01: "Австрия (A)", 0x02: "Албания (AL)", 0x03: "Андорра (AND)", 0x04: "Азербайджан (AZ)",
    0x05: "Бельгия (B)", 0x06: "Болгария (BG)", 0x07: "Босния и Герцеговина (BIH)", 0x08: "Беларусь (BY)",
    0x09: "Швейцария (CH)", 0x0A: "Кипр (CY)", 0x0B: "Чехия (CZ)", 0x0C: "Германия (D)",
    0x0D: "Дания (DK)", 0x0E: "Испания (E)", 0x0F: "Эстония (EST)", 0x10: "Франция (F)",
    0x11: "Финляндия (FIN)", 0x12: "Лихтенштейн (FL)", 0x13: "Фарерские о-ва (FR)", 0x14: "Великобритания (UK)",
    0x15: "Грузия (GE)", 0x16: "Греция (GR)", 0x17: "Венгрия (H)", 0x18: "Хорватия (HR)",
    0x19: "Италия (I)", 0x1A: "Ирландия (IRL)", 0x1B: "Исландия (IS)", 0x1C: "Казахстан (KZ)",
    0x1D: "Люксембург (L)", 0x1E: "Литва (LT)", 0x1F: "Латвия (LV)", 0x20: "Мальта (M)",
    0x21: "Монако (MC)", 0x22: "Молдова (MD)", 0x23: "Молдова (MD)", 0x24: "Северная Македония (MK)",
    0x25: "Норвегия (N)", 0x26: "Нидерланды (NL)", 0x27: "Португалия (P)", 0x28: "Польша (PL)",
    0x29: "Румыния (RO)", 0x2A: "Сан-Марино (RSM)", 0x2B: "Россия (RUS)", 0x2C: "Швеция (S)",
    0x2D: "Словакия (SK)", 0x2E: "Словения (SLO)", 0x2F: "Туркменистан (TM)", 0x30: "Турция (TR)",
    0x31: "Украина (UA)", 0x32: "Ватикан (V)", 0x33: "Югославия (YU)",
}

CALIBRATION_PURPOSES = {
    0: "Резерв",
    1: "Активация (Activation)",
    2: "Первичная установка (First installation)",
    3: "Установка после ремонта (Installation after repair)",
    4: "Периодическая проверка (Periodic inspection / calibration)",
}

def decode_timereal(val: int) -> str:
    if not val or val == 0xFFFFFFFF:
        return "-"
    try:
        dt = datetime.datetime.fromtimestamp(val, tz=datetime.timezone.utc)
        return dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return str(val)

def parse_name(b: bytes) -> str:
    """Decodes Name structure (1 byte code page + string)."""
    if not b:
        return ""
    code_page = b[0]
    raw_str = b[1:]
    encodings = ["utf-8", "latin-1", "cp1251", "cp1252", "iso-8859-1"]
    for enc in encodings:
        try:
            res = raw_str.decode(enc).strip()
            if res:
                return res
        except Exception:
            continue
    return raw_str.decode("latin-1", errors="ignore").strip()

class ParsedDDD:
    def __init__(self, raw_bytes: bytes, filename: str = ""):
        self.filename = filename
        self.raw_bytes = raw_bytes
        self.file_size = len(raw_bytes)
        
        # Maps of raw extracted blocks
        self.data_blocks: Dict[int, bytes] = {}
        self.signature_blocks: Dict[int, bytes] = {}
        self.block_records: List[Dict[str, Any]] = []

        # Parsed high-level fields
        self.card_type_id: int = 1
        self.card_type_name: str = "Карта водителя (Driver Card)"
        self.member_state_code: int = 0
        self.member_state_name: str = "Неизвестно"
        self.card_number: str = ""
        self.issuing_authority: str = ""
        self.issue_date: str = ""
        self.validity_begin: str = ""
        self.validity_end: str = ""
        
        # Holder details
        self.holder_surname: str = ""
        self.holder_firstnames: str = ""
        self.birth_date: str = ""
        self.preferred_language: str = ""
        
        # Workshop specific
        self.workshop_name: str = ""
        self.workshop_address: str = ""
        self.calibrations_count_download: int = 0
        self.calibrations: List[Dict[str, Any]] = []

        # Driver specific
        self.driving_licence_num: str = ""
        self.driving_licence_authority: str = ""
        self.last_card_download: str = ""
        self.vehicles_used: List[Dict[str, Any]] = []
        self.places: List[Dict[str, Any]] = []

        self._parse_tlv()
        self._decode_content()

    def _parse_tlv(self):
        pos = 0
        data = self.raw_bytes
        while pos + 5 <= len(data):
            fid, tag_type, length = struct.unpack(">HBH", data[pos:pos+5])
            pos += 5
            payload = data[pos:pos+length]
            pos += length

            is_data = (tag_type in (0, 2))
            is_sig = (tag_type in (1, 3))

            if is_data:
                self.data_blocks[fid] = payload
            elif is_sig:
                self.signature_blocks[fid] = payload

            self.block_records.append({
                "fid": fid,
                "fid_hex": f"0x{fid:04X}",
                "tag_type": tag_type,
                "kind": "DATA" if is_data else "SIGNATURE",
                "length": length,
                "offset": pos - 5 - length,
            })

    def _decode_content(self):
        # 1. EF_Application_Identification (0x0501)
        if 0x0501 in self.data_blocks:
            p = self.data_blocks[0x0501]
            if len(p) >= 1:
                self.card_type_id = p[0]
                if self.card_type_id == 2:
                    self.card_type_name = "Карта мастерской (Workshop Card)"
                elif self.card_type_id == 1:
                    self.card_type_name = "Карта водителя (Driver Card)"
                elif self.card_type_id == 3:
                    self.card_type_name = "Карта инспектора / контроля (Control Card)"
                elif self.card_type_id == 4:
                    self.card_type_name = "Карта компании (Company Card)"

        # 2. EF_Identification (0x0520)
        if 0x0520 in self.data_blocks:
            p = self.data_blocks[0x0520]
            if len(p) >= 65:
                self.member_state_code = p[0]
                self.member_state_name = NATION_CODES.get(p[0], f"Код {p[0]}")
                raw_cnum = p[1:17].decode("ascii", errors="ignore").strip()
                self.card_number = "".join(c for c in raw_cnum if c.isalnum() or c in "-_")
                self.issuing_authority = parse_name(p[17:53])
                self.issue_date = decode_timereal(int.from_bytes(p[53:57], "big"))
                self.validity_begin = decode_timereal(int.from_bytes(p[57:61], "big"))
                self.validity_end = decode_timereal(int.from_bytes(p[61:65], "big"))

            # Workshop identification (offset 65: 36 workshopName + 36 workshopAddress + 36 surname + 36 firstnames + 2 lang)
            if self.card_type_id == 2 and len(p) >= 65 + 146:
                self.workshop_name = parse_name(p[65:101])
                self.workshop_address = parse_name(p[101:137])
                self.holder_surname = parse_name(p[137:173])
                self.holder_firstnames = parse_name(p[173:209])
                self.preferred_language = p[209:211].decode("ascii", errors="ignore").strip()

            # Driver identification (offset 65: 36 surname + 36 firstnames + 4 birthdate + 2 lang)
            elif len(p) >= 65 + 78:
                self.holder_surname = parse_name(p[65:101])
                self.holder_firstnames = parse_name(p[101:137])
                # Datef (4 bytes BCD: YYYYMMDD)
                b_date = p[137:141]
                try:
                    self.birth_date = f"{b_date[3]:02X}.{b_date[2]:02X}.{b_date[0]:02X}{b_date[1]:02X}"
                except Exception:
                    self.birth_date = b_date.hex()
                self.preferred_language = p[141:143].decode("ascii", errors="ignore").strip()

        # 3. EF_Driving_Licence_Info (0x0521)
        if 0x0521 in self.data_blocks:
            p = self.data_blocks[0x0521]
            if len(p) >= 36:
                self.driving_licence_authority = parse_name(p[:36])
                if len(p) > 37:
                    raw_dl = p[37:].decode("ascii", errors="ignore").strip()
                    self.driving_licence_num = "".join(c for c in raw_dl if c.isalnum() or c in " -_")

        # 4. EF_Card_Download (0x050E for Driver, 0x0509 for Workshop)
        if 0x050E in self.data_blocks and len(self.data_blocks[0x050E]) >= 4:
            self.last_card_download = decode_timereal(int.from_bytes(self.data_blocks[0x050E][:4], "big"))
        if 0x0509 in self.data_blocks and len(self.data_blocks[0x0509]) >= 2:
            self.calibrations_count_download = int.from_bytes(self.data_blocks[0x0509][:2], "big")

        # 5. EF_Calibration_Data (0x050A) - Workshop records
        if 0x050A in self.data_blocks:
            p = self.data_blocks[0x050A]
            if len(p) > 3:
                tot, ptr = struct.unpack(">HB", p[:3])
                rec_size = 105
                num_recs = (len(p) - 3) // rec_size
                for i in range(num_recs):
                    rec = p[3 + i*rec_size : 3 + (i+1)*rec_size]
                    if len(rec) < rec_size:
                        continue
                    purpose_id = rec[0]
                    vin = rec[1:18].decode("ascii", errors="ignore").strip()
                    reg_nation_id = rec[18]
                    plate = parse_name(rec[19:33])
                    w_c, k_c, l_t = struct.unpack(">HHH", rec[33:39])
                    raw_tyre = rec[39:54].decode("latin-1", errors="ignore").replace("\x00", "").strip()
                    tyre = "".join(c for c in raw_tyre if c.isprintable())
                    speed = rec[54]
                    odo = int.from_bytes(rec[58:61], "big")
                    calib_t = int.from_bytes(rec[65:69], "big")
                    next_t = int.from_bytes(rec[69:73], "big")
                    vu_part = rec[73:89].decode("ascii", errors="ignore").strip()
                    vu_serial = rec[89:97].hex().upper()

                    if vin or plate:
                        self.calibrations.append({
                            "index": len(self.calibrations) + 1,
                            "purpose": CALIBRATION_PURPOSES.get(purpose_id, f"Код {purpose_id}"),
                            "vin": vin,
                            "plate": plate,
                            "nation": NATION_CODES.get(reg_nation_id, str(reg_nation_id)),
                            "odo": odo,
                            "date": decode_timereal(calib_t),
                            "next_date": decode_timereal(next_t),
                            "vu_part": vu_part,
                            "vu_serial": vu_serial,
                            "w": w_c,
                            "k": k_c,
                            "l": l_t,
                            "tyre": tyre,
                            "speed": speed,
                        })

        # 6. EF_Vehicles_Used (0x0505) - Driver records
        if 0x0505 in self.data_blocks:
            p = self.data_blocks[0x0505]
            if len(p) > 2:
                rec_len = 31
                num_recs = (len(p) - 2) // rec_len
                for i in range(num_recs):
                    rec = p[2 + i*rec_len : 2 + (i+1)*rec_len]
                    if len(rec) < rec_len:
                        continue
                    odo_b = int.from_bytes(rec[0:3], "big")
                    odo_e = int.from_bytes(rec[3:6], "big")
                    t_first = int.from_bytes(rec[6:10], "big")
                    t_last = int.from_bytes(rec[10:14], "big")
                    nat = rec[14]
                    raw_plate = rec[15:29].decode("latin-1", errors="ignore").strip()
                    clean_plate = "".join(c for c in raw_plate if c.isalnum() or c in " -_")
                    if clean_plate:
                        self.vehicles_used.append({
                            "index": len(self.vehicles_used) + 1,
                            "plate": clean_plate,
                            "nation": NATION_CODES.get(nat, str(nat)),
                            "odo_begin": odo_b,
                            "odo_end": odo_e,
                            "km_driven": max(0, odo_e - odo_b),
                            "first_use": decode_timereal(t_first),
                            "last_use": decode_timereal(t_last),
                        })

        # 7. EF_Places (0x0506) - Driver records
        if 0x0506 in self.data_blocks:
            p = self.data_blocks[0x0506]
            if len(p) > 1:
                rec_len = 10
                num_recs = (len(p) - 1) // rec_len
                for i in range(num_recs):
                    rec = p[1 + i*rec_len : 1 + (i+1)*rec_len]
                    if len(rec) < rec_len:
                        continue
                    t_entry = int.from_bytes(rec[0:4], "big")
                    entry_type = rec[4]
                    nat = rec[5]
                    odo = int.from_bytes(rec[7:10], "big")
                    type_str = "Начало смены (Start)" if entry_type == 0 else "Окончание смены (End)" if entry_type == 1 else f"Тип {entry_type}"
                    if t_entry and t_entry != 0xFFFFFFFF:
                        self.places.append({
                            "index": len(self.places) + 1,
                            "time": decode_timereal(t_entry),
                            "type": type_str,
                            "nation": NATION_CODES.get(nat, str(nat)),
                            "odo": odo,
                        })

def load_ddd_file(filepath: str) -> ParsedDDD:
    with open(filepath, "rb") as f:
        content = f.read()
    return ParsedDDD(content, filename=filepath)
