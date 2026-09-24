"""
TahoCard Dumper - Application Entry Point
Supports both GUI mode (default) and CLI mode for headless dumping and automation.
"""

import sys
import os
import argparse
import traceback

def emergency_show_error(err_msg: str):
    """Fallback error reporting before GUI or logger is initialized."""
    try:
        with open("crash.log", "a", encoding="utf-8") as f:
            f.write(err_msg + "\n\n")
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, err_msg, "TahoDumper - Ошибка запуска", 0x10)
        except Exception:
            pass
    print(err_msg, file=sys.stderr)

# Ensure proper encoding on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.logger import setup_logger, logger, get_app_dir
from src.card_reader import TachographReader
from src.ddd_builder import save_ddd_file, parse_card_identification

def run_cli_dump(reader_index: int = 0, pin: str = ""):
    setup_logger()
    logger.info("Starting CLI card dump...")

    readers = TachographReader.list_readers()
    if not readers:
        logger.error("Смарт-карт ридеры не найдены.")
        sys.exit(1)

    if reader_index >= len(readers):
        logger.error(f"Указанный индекс ридера {reader_index} недопустим. Доступно: {len(readers)}")
        sys.exit(1)

    target_reader = readers[reader_index]
    logger.info(f"Используется ридер [{reader_index}]: {target_reader}")

    card = TachographReader()
    if not card.connect(target_reader):
        logger.error("Не удалось подключиться к карте.")
        sys.exit(1)

    try:
        def on_progress(percent, text, count):
            logger.info(f"[{percent:5.1f}%] {text}")

        ef_map, sig_map = card.dump_all_efs(pin_str=pin, progress_callback=on_progress)
        if not ef_map:
            logger.error("Не удалось прочитать ни один EF с карты.")
            sys.exit(1)

        app_dir = get_app_dir()
        dumps_dir = f"{app_dir}/dumps"
        out_path, total_bytes = save_ddd_file(ef_map, dumps_dir, ef_signatures_map=sig_map)

        info = {}
        if 0x0520 in ef_map:
            info = parse_card_identification(ef_map[0x0520])

        logger.info("=" * 50)
        logger.info("Дамп успешно создан!")
        logger.info(f"Файл: {out_path}")
        logger.info(f"Размер: {total_bytes} байт")
        if info.get("card_number"):
            logger.info(f"Номер карты: {info['card_number']}")
        if info.get("holder_surname") or info.get("holder_name"):
            logger.info(f"Владелец: {info.get('holder_surname', '')} {info.get('holder_name', '')}")
        logger.info("=" * 50)

    finally:
        card.disconnect()

def main():
    parser = argparse.ArgumentParser(description="TahoCard Dumper - Tachograph Card Reader & Dumper")
    parser.add_argument("--cli", action="store_true", help="Запустить в консольном режиме без GUI")
    parser.add_argument("--reader", type=int, default=0, help="Индекс ридера для CLI режима (по умолчанию 0)")
    parser.add_argument("--pin", type=str, default="", help="PIN-код для карты мастерской")
    parser.add_argument("--list-readers", action="store_true", help="Вывести список обнаруженных ридеров и выйти")

    args = parser.parse_args()

    if args.list_readers:
        readers = TachographReader.list_readers()
        if readers:
            print("Доступные считыватели:")
            for i, r in enumerate(readers):
                print(f"  [{i}] {r}")
        else:
            print("Считыватели не найдены.")
        sys.exit(0)

    if args.cli:
        run_cli_dump(reader_index=args.reader, pin=args.pin)
    else:
        # Launch graphical user interface
        from src.gui import run_app
        run_app()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        emergency_show_error(f"Необработанная ошибка:\n\n{traceback.format_exc()}")
        sys.exit(1)
