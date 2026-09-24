from __future__ import annotations

"""
Tachograph Constants and Specifications
Based on EU Council Regulation (EEC) No 3821/85 Annex 1B and Commission Implementing Regulation (EU) 2016/799 Annex 1C.
"""

# Application Identifiers (AID)
# Annex 1B (Gen 1): 'FF 54 41 43 48 4F' ("TACHO" with 0xFF tag)
AID_TACHO_GEN1 = [0xFF, 0x54, 0x41, 0x43, 0x48, 0x4F]

# Annex 1C (Gen 2 Smart Tachograph):
AID_TACHO_GEN2 = [0xA0, 0x00, 0x00, 0x00, 0x18, 0x40, 0x00, 0x00, 0x01, 0x63, 0x61, 0x72, 0x64, 0x69, 0x64, 0x00]

# APDU Commands
def apdu_select_aid(aid: list[int], p2: int = 0x0C) -> list[int]:
    """Select Application by AID (P1=0x04, P2=0x0C or 0x00)."""
    return [0x00, 0xA4, 0x04, p2, len(aid)] + aid

def apdu_select_ef(fid: int, p2: int = 0x0C) -> list[int]:
    """Select Elementary File (EF) by File Identifier (FID)."""
    hi = (fid >> 8) & 0xFF
    lo = fid & 0xFF
    return [0x00, 0xA4, 0x02, p2, 0x02, hi, lo]

def apdu_read_binary(offset: int, length: int) -> list[int]:
    """
    Read Binary command (ISO 7816-4).
    offset: 0 .. 32767
    length: 1 .. 256 (0x00 represents 256 bytes)
    """
    p1 = (offset >> 8) & 0x7F
    p2 = offset & 0xFF
    le = length if length < 256 else 0x00
    return [0x00, 0xB0, p1, p2, le]

def apdu_verify_pin(pin_bytes: list[int]) -> list[int]:
    """
    VERIFY CHV command for workshop card (ISO 7816-4).
    CLA=0x00, INS=0x20, P1=0x00, P2=0x01 (CHV 1), Lc=0x08
    """
    padded = list(pin_bytes)
    while len(padded) < 8:
        padded.append(0xFF)
    return [0x00, 0x20, 0x00, 0x01, 0x08] + padded[:8]


# Security Operations for Card Download (Annex 1B/1C Appendix 7)
APDU_PERFORM_HASH_OF_FILE = [0x80, 0x2A, 0x90, 0x00]
APDU_COMPUTE_DIGITAL_SIGNATURE = [0x00, 0x2A, 0x9E, 0x9A, 0x80] # 128 bytes RSA signature for Gen1

# Files that do NOT have digital signatures (per Appendix 7 / Annex 1B & 1C)
# 0x0002 (EF_ICC) and 0x0005 (EF_IC) are in MF root; Certificates are keys themselves
UNSIGNED_FIDS = {
    0x0002,  # EF_ICC
    0x0005,  # EF_IC
    0xC100,  # EF_Card_Certificate
    0xC108,  # EF_CA_Certificate
    0xC101,  # EF_Card_Sign_Certificate (Gen 2)
    0xC102,  # EF_Card_MA_Certificate (Gen 2)
    0xC103,  # EF_Card_EAC_Certificate (Gen 2)
    0xC109,  # EF_Link_Certificate (Gen 2)
    0x050E,  # EF_Card_Download (Driver) - NOT signed per Appendix 7 DDP_035
    0x0509,  # EF_Card_Download_Workshop - NOT signed per Appendix 7 DDP_035
    0x2F00,  # EF_DIR
    0x2F01,  # EF_ATR_INFO
}

# Equipment / Card Types (Annex 1B CardType)
CARD_TYPE_DRIVER = 1
CARD_TYPE_WORKSHOP = 2
CARD_TYPE_CONTROL = 3
CARD_TYPE_COMPANY = 4
CARD_TYPE_PREFIXES = {
    CARD_TYPE_DRIVER: "C",
    CARD_TYPE_WORKSHOP: "W",
    CARD_TYPE_CONTROL: "K",
    CARD_TYPE_COMPANY: "S",
}
# Elementary Files (EF) Definitions for Tachograph Cards
# (FID, Name, Description, is_critical, min_size)
EF_DEFINITIONS = [
    # General / Card identification
    (0x0002, "EF_ICC", "Card identification (ICC manufacturer & serial)", True),
    (0x0005, "EF_IC", "IC identification (chip component info)", True),
    (0x0501, "EF_Application_Identification", "Tachograph application info & card type", True),
    (0xC100, "EF_Card_Certificate", "Card digital certificate", True),
    (0xC108, "EF_CA_Certificate", "Member State CA certificate", True),
    (0x0520, "EF_Identification", "Cardholder & driving licence details", True),
    (0x050E, "EF_Card_Download", "Last card download record", False),
    (0x0521, "EF_Driving_Licence_Info", "Driving licence information", False),

    # Activities & usage (Annex 1B Driver Card)
    (0x0502, "EF_Events_Data", "Recorded events (overspeed, tampering)", False),
    (0x0503, "EF_Faults_Data", "Recorded faults (sensor faults, power failure)", False),
    (0x0504, "EF_Driver_Activity_Data", "Driver activity data (driving/work/rest log)", True),
    (0x0505, "EF_Vehicles_Used", "Vehicles used by driver", True),
    (0x0506, "EF_Places", "Places entered (start/end of work periods)", True),
    (0x0507, "EF_Current_Usage", "Current session and vehicle usage", False),
    (0x0508, "EF_Control_Activity_Data", "Control / police inspection records", False),
    (0x0522, "EF_Specific_Conditions", "Specific conditions (ferry, out of scope)", False),

    # Workshop card specific
    (0x0509, "EF_Calibration", "Workshop calibration record", False),
    (0x050A, "EF_Calibration_Data", "Detailed workshop calibration records", False),
    (0x050B, "EF_Sensor_Installation_Data", "Motion sensor installation records", False),

    # Gen 2 / Smart Tachograph (Annex 1C)
    (0x0523, "EF_GNSS_Places", "GNSS position records (Smart Tacho)", False),
    (0x0524, "EF_VehicleUnits_Used", "Vehicle units used (Gen 2)", False),
    (0x0525, "EF_GNSS_Places_Extended", "Extended GNSS places", False),
    (0x0526, "EF_Places_Authentication", "Places digital signature/authentication", False),
    (0x0527, "EF_GNSS_Places_Authentication", "GNSS authentication data", False),
    (0x0528, "EF_Specific_Conditions_Extended", "Specific conditions (Gen 2)", False),
    (0xC101, "EF_Card_Sign_Certificate", "Card signature certificate (Gen 2)", False),
    (0xC102, "EF_Card_MA_Certificate", "Card mutual authentication cert (Gen 2)", False),
    (0xC103, "EF_Card_EAC_Certificate", "Card EAC certificate (Gen 2)", False),
    (0x050F, "EF_Card_Download_Gen2", "Card download record (Gen 2)", False),
]

# SW1 SW2 Status Words translation
SW_DESCRIPTIONS = {
    0x9000: "Успешно (Success)",
    0x6100: "Успешно, доступны данные",
    0x6281: "Предупреждение: возвращенные данные могут быть повреждены",
    0x6282: "Конец файла достигнут до чтения запрошенного количества байт",
    0x6300: "Ошибка проверки",
    0x6400: "Состояние энергонезависимой памяти не изменилось",
    0x6581: "Ошибка памяти при записи/чтении",
    0x6700: "Неверная длина поля данных (Wrong length)",
    0x6981: "Команда несовместима со структурой файла",
    0x6982: "Условие безопасности не удовлетворено (требуется PIN / аутентификация)",
    0x6983: "Метод аутентификации заблокирован (PIN заблокирован)",
    0x6984: "Данные ссылки непригодны",
    0x6985: "Условия использования не соблюдены",
    0x6A80: "Неверные данные в команде",
    0x6A81: "Функция не поддерживается",
    0x6A82: "Файл или приложение не найдено (File / AID not found)",
    0x6A83: "Запись не найдена",
    0x6A84: "Недостаточно памяти в файле",
    0x6A86: "Неверные параметры P1-P2",
    0x6A88: "Данные не найдены",
    0x6B00: "Смещение за пределами файла (EOF reached)",
    0x6C00: "Неверное значение Le",
    0x6D00: "Команда INS не поддерживается",
    0x6E00: "Класс CLA не поддерживается",
    0x6F00: "Неизвестная внутренняя ошибка карты",
}

def describe_sw(sw1: int, sw2: int) -> str:
    """Return human readable description of SW1 SW2 status bytes."""
    full_sw = (sw1 << 8) | sw2
    if full_sw in SW_DESCRIPTIONS:
        return SW_DESCRIPTIONS[full_sw]
    if sw1 == 0x61:
        return f"Успешно, доступно {sw2} байт"
    if sw1 == 0x6C:
        return f"Неверная длина Le, точная длина: {sw2} байт"
    if sw1 == 0x63 and (sw2 & 0xF0) == 0xC0:
        attempts = sw2 & 0x0F
        return f"Неверный PIN. Осталось попыток: {attempts}"
    base_sw = (sw1 << 8)
    if base_sw in SW_DESCRIPTIONS:
        return SW_DESCRIPTIONS[base_sw]
    return f"Статус: {sw1:02X} {sw2:02X}"
