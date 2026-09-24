from __future__ import annotations

"""
Smart Card Reader and Tachograph APDU Protocol Handler
Manages PC/SC communication via pyscard, handles card detection, PIN verification,
adaptive binary reading of Tachograph Elementary Files (EF), and support for both MF and DF.
"""

import time
from typing import List, Dict, Optional, Callable, Tuple

try:
    from smartcard.System import readers as pcsc_readers
    from smartcard.CardConnection import CardConnection
    from smartcard.Exceptions import NoCardException, CardConnectionException
    from smartcard.pcsc.PCSCExceptions import EstablishContextException
    PYSCARD_AVAILABLE = True
except ImportError:
    PYSCARD_AVAILABLE = False
    pcsc_readers = None

from .logger import logger, format_hex
from .tacho_constants import (
    AID_TACHO_GEN1,
    AID_TACHO_GEN2,
    EF_DEFINITIONS,
    APDU_PERFORM_HASH_OF_FILE,
    APDU_COMPUTE_DIGITAL_SIGNATURE,
    UNSIGNED_FIDS,
    apdu_select_aid,
    apdu_select_ef,
    apdu_read_binary,
    apdu_verify_pin,
    describe_sw,
)

# Files located directly under Master File (MF 3F00)
MF_FILES = [
    (0x0002, "EF_ICC", "Card identification (ICC manufacturer & serial)", True),
    (0x0005, "EF_IC", "IC identification (chip component info)", True),
]

# Files located under Dedicated File Tachograph (DF TACHO)
DF_FILES = [ef for ef in EF_DEFINITIONS if ef[0] not in (0x0002, 0x0005)]

class TachographReader:
    def __init__(self):
        self.connection = None
        self.current_reader_name: Optional[str] = None
        self.card_atr: str = ""
        self.is_connected = False

    @staticmethod
    def list_readers() -> List[str]:
        """
        Scans PC/SC subsystem for available smart card readers.
        Returns list of reader names or empty list if none found.
        """
        if not PYSCARD_AVAILABLE:
            logger.error("pyscard library is not installed or available.")
            return []

        try:
            r_list = pcsc_readers()
            names = [str(r) for r in r_list]
            logger.debug(f"Detected {len(names)} reader(s): {names}")
            return names
        except EstablishContextException as e:
            logger.warning(f"PC/SC SCardEstablishContext failed (SCardSvr service may be stopped): {e}")
            return []
        except Exception as e:
            logger.error(f"Error enumerating PC/SC readers: {e}", exc_info=True)
            return []

    def connect(self, reader_name: str) -> bool:
        """Connects to the smart card inserted in the specified reader."""
        self.disconnect()
        if not PYSCARD_AVAILABLE:
            logger.error("pyscard not available.")
            return False

        try:
            available = pcsc_readers()
            target_reader = None
            for r in available:
                if str(r) == reader_name:
                    target_reader = r
                    break

            if not target_reader:
                logger.error(f"Reader '{reader_name}' not found among available devices.")
                return False

            logger.info(f"Connecting to reader: {reader_name}")
            self.connection = target_reader.createConnection()
            self.connection.connect(CardConnection.T0_protocol | CardConnection.T1_protocol)
            self.current_reader_name = reader_name
            self.is_connected = True

            atr_bytes = self.connection.getATR()
            self.card_atr = format_hex(atr_bytes)
            logger.info(f"Connected successfully. Card ATR: {self.card_atr}")
            return True

        except NoCardException:
            logger.warning(f"No card present in reader '{reader_name}'.")
            return False
        except CardConnectionException as e:
            logger.error(f"Card connection failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected connection error: {e}", exc_info=True)
            return False

    def disconnect(self):
        """Disconnects current card session."""
        if self.connection and self.is_connected:
            try:
                self.connection.disconnect()
                logger.debug(f"Disconnected from reader '{self.current_reader_name}'.")
            except Exception as e:
                logger.debug(f"Disconnect notice: {e}")
        self.connection = None
        self.is_connected = False
        self.current_reader_name = None
        self.card_atr = ""

    def transmit(self, apdu: List[int]) -> Tuple[List[int], int, int]:
        """
        Sends APDU command to card with full debug logging.
        Handles GET RESPONSE (0x61) and WRONG LE (0x6C) automatically.
        """
        if not self.connection or not self.is_connected:
            raise RuntimeError("Smart card reader is not connected.")

        logger.debug(f"TX: {format_hex(apdu)}")
        data, sw1, sw2 = self.connection.transmit(apdu)
        sw_desc = describe_sw(sw1, sw2)
        logger.debug(f"RX: {sw1:02X} {sw2:02X} ({sw_desc}), Data len={len(data)}: {format_hex(data[:32])}{'...' if len(data) > 32 else ''}")

        # Handle 6C XX: Wrong length Le -> re-issue command with exact length requested by card
        if sw1 == 0x6C:
            logger.debug(f"Card requested Le={sw2:02X}, re-issuing command...")
            apdu_retry = list(apdu)
            apdu_retry[-1] = sw2
            return self.transmit(apdu_retry)

        # Handle 61 XX: SW=61XX means XX bytes available via GET RESPONSE (T=0)
        if sw1 == 0x61:
            le = sw2 if sw2 != 0 else 0x00
            get_response = [0x00, 0xC0, 0x00, 0x00, le]
            logger.debug(f"Sending GET RESPONSE for {sw2} bytes: {format_hex(get_response)}")
            resp_data, r_sw1, r_sw2 = self.connection.transmit(get_response)
            logger.debug(f"GET RESPONSE RX: {r_sw1:02X} {r_sw2:02X}, len={len(resp_data)}")
            data = data + resp_data
            sw1, sw2 = r_sw1, r_sw2

        return data, sw1, sw2

    def select_master_file(self) -> bool:
        """Attempts to ensure we are at Master File level (MF 3F00)."""
        logger.info("Checking Master File (MF) root files...")
        # Right after ATR, card is already positioned at MF.
        # We also try P1=0x00 or P1=0x01 with 3F00 if needed.
        candidates = [
            [0x00, 0xA4, 0x00, 0x0C, 0x02, 0x3F, 0x00],
            [0x00, 0xA4, 0x00, 0x00, 0x02, 0x3F, 0x00],
        ]
        for apdu in candidates:
            try:
                data, sw1, sw2 = self.transmit(apdu)
                if sw1 == 0x90 or sw1 == 0x61:
                    logger.info("Positioned at Master File (MF).")
                    return True
            except Exception:
                pass
        # Even if explicit MF select returned 6A86, card may already be at MF after ATR
        return True

    def select_tachograph_application(self) -> Tuple[bool, str]:
        """
        Selects tachograph dedicated file / application.
        Tries Annex 1B (Gen 1) AID first, then Annex 1C (Gen 2) AID.
        """
        logger.info("Selecting Tachograph application...")

        # 1. Try Gen 1 AID: FF 54 41 43 48 4F
        for p2 in [0x0C, 0x00]:
            apdu = apdu_select_aid(AID_TACHO_GEN1, p2=p2)
            try:
                _, sw1, sw2 = self.transmit(apdu)
                if sw1 == 0x90 and sw2 == 0x00:
                    logger.info("Successfully selected Tachograph Gen 1 application (Annex 1B).")
                    return True, "Gen 1 (Annex 1B)"
            except Exception as e:
                logger.debug(f"AID Gen 1 attempt error: {e}")

        # 2. Try Gen 2 AID
        for p2 in [0x0C, 0x00]:
            apdu = apdu_select_aid(AID_TACHO_GEN2, p2=p2)
            try:
                _, sw1, sw2 = self.transmit(apdu)
                if sw1 == 0x90 and sw2 == 0x00:
                    logger.info("Successfully selected Tachograph Gen 2 application (Annex 1C).")
                    return True, "Gen 2 (Annex 1C)"
            except Exception as e:
                logger.debug(f"AID Gen 2 attempt error: {e}")

        logger.error("Failed to select tachograph application on card.")
        return False, "Unknown"

    def verify_pin(self, pin_str: str) -> Tuple[bool, str]:
        """
        Sends PIN verification command for workshop cards.
        """
        if not pin_str:
            return True, "PIN not provided (skipped)"

        logger.info(f"Verifying card PIN ({len(pin_str)} digits)...")
        pin_bytes = [ord(c) for c in pin_str]
        apdu = apdu_verify_pin(pin_bytes)
        data, sw1, sw2 = self.transmit(apdu)

        if sw1 == 0x90 and sw2 == 0x00:
            logger.info("PIN accepted successfully.")
            return True, "PIN принят успешно"
        else:
            msg = describe_sw(sw1, sw2)
            logger.warning(f"PIN verification failed: SW={sw1:02X}{sw2:02X} ({msg})")
            return False, f"Ошибка PIN ({sw1:02X}{sw2:02X}): {msg}"

    def read_binary_chunk_adaptive(self, offset: int, default_len: int = 128) -> Tuple[bytes, int, int]:
        """
        Reads a binary chunk at offset.
        If the card rejects with SW=6700 (Wrong length Le exceeds file/record boundary),
        adapts length using binary search to read the exact remaining bytes.
        """
        apdu = apdu_read_binary(offset, default_len)
        chunk, sw1, sw2 = self.transmit(apdu)

        if sw1 == 0x90 and sw2 == 0x00:
            return bytes(chunk), sw1, sw2

        # 67 00: Wrong Le length -> file has fewer bytes remaining than default_len
        if (sw1, sw2) == (0x67, 0x00):
            logger.debug(f"SW 67 00 received at offset {offset}. Starting adaptive length probe...")

            # 1. Try Le = 0x00 (requests maximum available or triggers 6C XX)
            p1 = (offset >> 8) & 0x7F
            p2 = offset & 0xFF
            apdu_zero = [0x00, 0xB0, p1, p2, 0x00]
            chunk_z, z_sw1, z_sw2 = self.transmit(apdu_zero)
            if z_sw1 == 0x90 and z_sw2 == 0x00 and len(chunk_z) > 0:
                return bytes(chunk_z), z_sw1, z_sw2

            # 2. Binary search for remaining available length [1 .. default_len - 1]
            low = 1
            high = default_len - 1
            best_chunk: bytes = bytes()

            while low <= high:
                mid = (low + high) // 2
                probe_apdu = apdu_read_binary(offset, mid)
                p_data, p_sw1, p_sw2 = self.transmit(probe_apdu)

                if p_sw1 == 0x90 and p_sw2 == 0x00 and len(p_data) == mid:
                    best_chunk = bytes(p_data)
                    low = mid + 1  # Try reading more bytes
                elif (p_sw1, p_sw2) == (0x67, 0x00):
                    high = mid - 1  # Length too large, try smaller
                else:
                    # End of file or error
                    break

            if best_chunk:
                logger.debug(f"Adaptive probe succeeded: read {len(best_chunk)} bytes at offset {offset}.")
                return best_chunk, 0x90, 0x00

        return bytes(chunk), sw1, sw2

    def compute_file_signature(self, fid: int, ef_name: str) -> Optional[bytes]:
        """
        Computes SHA hash of currently selected EF and retrieves its digital signature
        per Annex 1B/1C Appendix 7 (Data downloading protocols).
        APDU 1: 80 2A 90 00 (PERFORM HASH OF FILE)
        APDU 2: 00 2A 9E 9A 80 (PSO: COMPUTE DIGITAL SIGNATURE, Le=128 bytes)
        """
        if fid in UNSIGNED_FIDS:
            return None

        try:
            logger.debug(f"Calculating card hash for EF 0x{fid:04X} ({ef_name})...")
            _, h_sw1, h_sw2 = self.transmit(APDU_PERFORM_HASH_OF_FILE)
            if h_sw1 != 0x90:
                logger.debug(f"PERFORM HASH OF FILE for EF 0x{fid:04X} returned SW={h_sw1:02X}{h_sw2:02X}")
                return None

            logger.debug(f"Requesting digital signature for EF 0x{fid:04X} ({ef_name})...")
            sig_data, s_sw1, s_sw2 = self.transmit(APDU_COMPUTE_DIGITAL_SIGNATURE)
            if s_sw1 == 0x90 and sig_data:
                logger.info(f"Digital signature obtained for EF 0x{fid:04X} ({ef_name}): {len(sig_data)} bytes.")
                return bytes(sig_data)
            else:
                logger.debug(f"COMPUTE DIGITAL SIGNATURE for EF 0x{fid:04X} returned SW={s_sw1:02X}{s_sw2:02X}")
                return None
        except Exception as e:
            logger.debug(f"Signature computation notice for EF 0x{fid:04X}: {e}")
            return None

    def read_elementary_file(self, fid: int, ef_name: str) -> Tuple[Optional[bytes], Optional[bytes]]:
        """
        Selects an EF by FID and reads its content via READ BINARY commands.
        Reads sequentially in chunks (128 bytes) adapting dynamically at file boundaries.
        Also calculates file hash and requests digital signature for signed EFs.
        Returns (data_bytes, signature_bytes).
        """
        logger.info(f"--- Selecting EF 0x{fid:04X} ({ef_name}) ---")

        # 1. Select EF (try P2=0x0C then P2=0x00, P2=0x04)
        selected = False
        for p2 in [0x0C, 0x00, 0x04]:
            apdu = apdu_select_ef(fid, p2=p2)
            data, sw1, sw2 = self.transmit(apdu)
            if sw1 == 0x90 and sw2 == 0x00:
                selected = True
                break
            elif sw1 == 0x61:
                selected = True
                break
            elif (sw1, sw2) == (0x6A, 0x82):
                logger.debug(f"EF 0x{fid:04X} not present on this card.")
                return None, None

        if not selected:
            logger.debug(f"EF 0x{fid:04X} selection returned SW={sw1:02X}{sw2:02X}")
            return None, None

        # 2. Read file content via READ BINARY
        file_bytes = bytearray()
        offset = 0
        chunk_size = 128

        while True:
            chunk, sw1, sw2 = self.read_binary_chunk_adaptive(offset, chunk_size)

            if sw1 == 0x90 and sw2 == 0x00:
                if not chunk:
                    break
                file_bytes.extend(chunk)
                offset += len(chunk)

                # If received fewer bytes than chunk_size, we reached exact EOF
                if len(chunk) < chunk_size:
                    break

            elif (sw1, sw2) in [(0x6B, 0x00), (0x62, 0x82), (0x67, 0x00), (0x6A, 0x86)]:
                # End of file reached
                logger.debug(f"EOF reached for EF 0x{fid:04X} at offset {offset}")
                break
            elif sw1 == 0x69 and sw2 == 0x82:
                logger.warning(
                    f"EF 0x{fid:04X} ({ef_name}) защищен условиями безопасности (SW=6982). "
                    f"Для считывания требуется ввод PIN-кода мастерской."
                )
                break
            else:
                logger.warning(f"Read binary stopped for EF 0x{fid:04X} at offset {offset}: SW={sw1:02X}{sw2:02X}")
                break

        data_bytes = bytes(file_bytes) if file_bytes else None
        sig_bytes = None
        if data_bytes:
            sig_bytes = self.compute_file_signature(fid, ef_name)

        sig_info = f", подпись: {len(sig_bytes)} байт." if sig_bytes else "."
        logger.info(f"EF 0x{fid:04X} ({ef_name}) read complete: {len(file_bytes)} bytes{sig_info}")
        return data_bytes, sig_bytes

    def dump_all_efs(
        self,
        pin_str: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str, int], None]] = None
    ) -> Tuple[Dict[int, bytes], Dict[int, bytes]]:
        """
        Performs full tachograph card dump:
        1. Selects Master File (MF) -> Reads EF_ICC, EF_IC
        2. Selects Tachograph Dedicated File (DF TACHO) -> Verifies PIN if supplied -> Reads all EFs
        3. Requests digital signatures for all signed EFs per Appendix 7.
        Returns tuple of (data_map, signatures_map).
        """
        results: Dict[int, bytes] = {}
        signatures: Dict[int, bytes] = {}
        all_ef_list = MF_FILES + DF_FILES
        total_efs = len(all_ef_list)
        processed_count = 0

        # Step 1: Read Master File (MF) files (EF_ICC 0x0002, EF_IC 0x0005)
        mf_ok = self.select_master_file()
        if mf_ok:
            for fid, name, desc, is_critical in MF_FILES:
                processed_count += 1
                percent = (processed_count / total_efs) * 100.0
                if progress_callback:
                    progress_callback(percent, f"Чтение {name} (0x{fid:04X})...", len(results))
                try:
                    data, sig = self.read_elementary_file(fid, name)
                    if data:
                        results[fid] = data
                        if sig:
                            signatures[fid] = sig
                except Exception as e:
                    logger.error(f"Error reading MF EF 0x{fid:04X} ({name}): {e}", exc_info=True)
        else:
            logger.debug("MF selection skipped or not supported directly.")

        # Step 2: Select Tachograph Dedicated File / Application
        app_ok, app_name = self.select_tachograph_application()
        if not app_ok:
            raise RuntimeError("Не удалось выбрать приложение тахографа на карте. Проверьте карту и считыватель.")

        # Step 3: Verify PIN if provided
        if pin_str:
            pin_ok, pin_msg = self.verify_pin(pin_str)
            if not pin_ok:
                raise RuntimeError(f"Ошибка проверки PIN: {pin_msg}")

        # Step 4: Read DF Tachograph EFs
        for fid, name, desc, is_critical in DF_FILES:
            processed_count += 1
            percent = (processed_count / total_efs) * 100.0
            if progress_callback:
                progress_callback(percent, f"Чтение {name} (0x{fid:04X})...", len(results))

            try:
                data, sig = self.read_elementary_file(fid, name)
                if data:
                    results[fid] = data
                    if sig:
                        signatures[fid] = sig
            except Exception as e:
                logger.error(f"Error reading DF EF 0x{fid:04X} ({name}): {e}", exc_info=True)

        if progress_callback:
            progress_callback(100.0, "Чтение завершено!", len(results))

        logger.info(
            f"Full dump complete. Successfully read {len(results)} Elementary Files, "
            f"{len(signatures)} digital signatures."
        )
        return results, signatures
