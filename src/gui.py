from __future__ import annotations

"""
Graphical User Interface for Taho Card Reader & Dumper
Built with Tkinter and TTK for native Windows appearance without extra dependencies.
"""

import os
import sys
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from typing import Optional

from .logger import setup_logger, set_gui_callback, get_app_dir, logger
from .card_reader import TachographReader
from .ddd_builder import save_ddd_file, parse_card_identification
from .viewer_window import DddViewerWindow

class TahoDumperApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TahoCard Dumper - Считыватель карт тахографа")
        self.geometry("760x650")
        self.minsize(680, 520)

        # Style configuration
        self.style = ttk.Style(self)
        self._setup_theme()

        # State
        self.reader = TachographReader()
        self.available_readers: list[str] = []
        self.is_dumping = False

        # Output and logs directories
        self.app_dir = get_app_dir()
        self.dumps_dir = os.path.join(self.app_dir, "dumps")
        os.makedirs(self.dumps_dir, exist_ok=True)

        # Build UI widgets
        self._build_ui()

        # Connect logger to GUI
        setup_logger(gui_callback=self._append_log_message)

        # Initial scan for readers
        self.after(200, self.refresh_readers)

    def _setup_theme(self):
        try:
            self.style.theme_use("vista" if "vista" in self.style.theme_names() else "clam")
        except Exception:
            pass

    def _build_ui(self):
        # 1. Header Frame
        header_frame = ttk.Frame(self, padding=(12, 10))
        header_frame.pack(fill=tk.X)

        title_label = ttk.Label(
            header_frame,
            text="Считыватель карт тахографа (PC/SC)",
            font=("Segoe UI", 14, "bold")
        )
        title_label.pack(anchor=tk.W)

        subtitle_label = ttk.Label(
            header_frame,
            text="Считывание данных с карт водителя и мастерской в формат .DDD (Annex 1B / 1C)",
            font=("Segoe UI", 9)
        )
        subtitle_label.pack(anchor=tk.W)

        # 2. Reader Selection Group
        reader_group = ttk.LabelFrame(self, text=" Считыватель смарт-карт (PC/SC) ", padding=10)
        reader_group.pack(fill=tk.X, padx=12, pady=5)

        r_select_frame = ttk.Frame(reader_group)
        r_select_frame.pack(fill=tk.X)

        ttk.Label(r_select_frame, text="Выберите ридер:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 8))

        self.reader_combobox = ttk.Combobox(r_select_frame, state="readonly", width=45)
        self.reader_combobox.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.reader_combobox.bind("<<ComboboxSelected>>", self._on_reader_selected)

        self.refresh_btn = ttk.Button(r_select_frame, text="🔄 Обновить", command=self.refresh_readers)
        self.refresh_btn.pack(side=tk.RIGHT)

        self.reader_status_lbl = ttk.Label(
            reader_group,
            text="Поиск считывателей...",
            font=("Segoe UI", 8),
            foreground="#555555"
        )
        self.reader_status_lbl.pack(anchor=tk.W, pady=(4, 0))

        # 3. Optional PIN Input Group
        pin_group = ttk.LabelFrame(self, text=" Параметры аутентификации (для карт мастерской) ", padding=10)
        pin_group.pack(fill=tk.X, padx=12, pady=5)

        pin_frame = ttk.Frame(pin_group)
        pin_frame.pack(fill=tk.X)

        ttk.Label(pin_frame, text="PIN-код (если требуется):").pack(side=tk.LEFT, padx=(0, 8))
        self.pin_entry = ttk.Entry(pin_frame, show="*", width=16)
        self.pin_entry.pack(side=tk.LEFT, padx=(0, 10))

        self.show_pin_var = tk.BooleanVar(value=False)
        show_pin_check = ttk.Checkbutton(
            pin_frame,
            text="Показать PIN",
            variable=self.show_pin_var,
            command=self._toggle_show_pin
        )
        show_pin_check.pack(side=tk.LEFT)

        ttk.Label(
            pin_group,
            text="* Для стандартных карт водителя PIN вводить не нужно (оставьте пустым).",
            font=("Segoe UI", 8),
            foreground="#666666"
        ).pack(anchor=tk.W, pady=(3, 0))

        # 4. Action & Progress Frame
        action_frame = ttk.Frame(self, padding=(12, 8))
        action_frame.pack(fill=tk.X)

        act_btn_row = ttk.Frame(action_frame)
        act_btn_row.pack(fill=tk.X)

        self.dump_btn = ttk.Button(
            act_btn_row,
            text="📥 Считать и сохранить дамп (.ddd)",
            command=self.start_dump,
            style="Accent.TButton" if "Accent.TButton" in self.style.theme_names() else "TButton"
        )
        self.dump_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6, padx=(0, 6))

        self.view_btn = ttk.Button(
            act_btn_row,
            text="🔍 Просмотр данных .DDD",
            command=self.open_viewer
        )
        self.view_btn.pack(side=tk.RIGHT, fill=tk.X, expand=True, ipady=6)

        self.progress_bar = ttk.Progressbar(action_frame, mode="determinate")
        self.progress_bar.pack(fill=tk.X, pady=(8, 4))

        self.status_lbl = ttk.Label(action_frame, text="Готов к работе", font=("Segoe UI", 9))
        self.status_lbl.pack(anchor=tk.W)

        # 5. Log & Console Frame
        log_group = ttk.LabelFrame(self, text=" Лог операций и отладка (debug) ", padding=8)
        log_group.pack(fill=tk.BOTH, expand=True, padx=12, pady=5)

        # Console controls
        btn_bar = ttk.Frame(log_group)
        btn_bar.pack(fill=tk.X, pady=(0, 4))

        open_dumps_btn = ttk.Button(btn_bar, text="📁 Папка с дампами", command=self.open_dumps_folder)
        open_dumps_btn.pack(side=tk.LEFT, padx=(0, 6))

        view_file_btn = ttk.Button(btn_bar, text="🔍 Открыть .DDD файл", command=self.open_viewer)
        view_file_btn.pack(side=tk.LEFT, padx=(0, 6))

        open_log_btn = ttk.Button(btn_bar, text="📜 Файл лога", command=self.open_log_file)
        open_log_btn.pack(side=tk.LEFT, padx=(0, 6))

        clear_log_btn = ttk.Button(btn_bar, text="🧹 Очистить", command=self.clear_console)
        clear_log_btn.pack(side=tk.RIGHT)

        # Scrolled Text
        self.log_text = scrolledtext.ScrolledText(
            log_group,
            wrap=tk.WORD,
            font=("Consolas", 8),
            background="#1e1e1e",
            foreground="#d4d4d4",
            insertbackground="#ffffff",
            state=tk.DISABLED
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Setup text tags for coloring
        self.log_text.tag_config("INFO", foreground="#9cdcfe")
        self.log_text.tag_config("WARNING", foreground="#ce9178")
        self.log_text.tag_config("ERROR", foreground="#f44747", font=("Consolas", 8, "bold"))
        self.log_text.tag_config("SUCCESS", foreground="#4ec9b0", font=("Consolas", 8, "bold"))
        self.log_text.tag_config("DEBUG", foreground="#808080")

    def _toggle_show_pin(self):
        if self.show_pin_var.get():
            self.pin_entry.config(show="")
        else:
            self.pin_entry.config(show="*")

    def _on_reader_selected(self, event=None):
        sel = self.reader_combobox.get()
        if sel and sel != "Ридеры не найдены":
            self.dump_btn.config(state=tk.NORMAL)
            self.reader_status_lbl.config(
                text=f"Выбран ридер: {sel}. Вставьте карту тахографа.",
                foreground="#006600"
            )
        else:
            self.dump_btn.config(state=tk.DISABLED)

    def refresh_readers(self):
        """Scans for available PC/SC card readers."""
        self.reader_status_lbl.config(text="Поиск подключенных считывателей...", foreground="#555555")
        self.refresh_btn.config(state=tk.DISABLED)

        def worker():
            readers = TachographReader.list_readers()
            self.after(0, lambda: self._update_readers_ui(readers))

        threading.Thread(target=worker, daemon=True).start()

    def _update_readers_ui(self, readers: list[str]):
        self.refresh_btn.config(state=tk.NORMAL)
        self.available_readers = readers

        if not readers:
            self.reader_combobox["values"] = ["Ридеры не найдены"]
            self.reader_combobox.current(0)
            self.dump_btn.config(state=tk.DISABLED)
            self.reader_status_lbl.config(
                text="Ридеры не найдены. Подключите PC/SC считыватель (Feitian R502) по USB и нажмите 'Обновить'.",
                foreground="#cc0000"
            )
            logger.warning("Считыватели смарт-карт не обнаружены.")
        else:
            self.reader_combobox["values"] = readers
            self.reader_combobox.current(0)
            self.dump_btn.config(state=tk.NORMAL)
            sel = readers[0]
            self.reader_status_lbl.config(
                text=f"Обнаружено ридеров: {len(readers)}. Готов к чтению.",
                foreground="#006600"
            )
            logger.info(f"Обнаружены считыватели: {readers}")

    def _append_log_message(self, message: str, levelname: str):
        """Appends formatted message to GUI log window from any thread."""
        def update():
            self.log_text.config(state=tk.NORMAL)
            tag = levelname if levelname in ["INFO", "WARNING", "ERROR", "DEBUG"] else "INFO"
            if "Успешно" in message or "Saved DDD" in message:
                tag = "SUCCESS"
            self.log_text.insert(tk.END, message + "\n", tag)
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)

        self.after(0, update)

    def clear_console(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

    def open_dumps_folder(self):
        """Opens dumps folder in Windows Explorer."""
        if os.name == "nt":
            os.startfile(self.dumps_dir)
        else:
            subprocess.Popen(["xdg-open", self.dumps_dir])

    def open_log_file(self):
        """Opens main debug log in default editor."""
        log_file = os.path.join(self.app_dir, "taho_debug.log")
        if os.path.exists(log_file):
            if os.name == "nt":
                os.startfile(log_file)
            else:
                subprocess.Popen(["xdg-open", log_file])
        else:
            messagebox.showinfo("Лог", "Файл лога еще не создан.")

    def start_dump(self):
        """Validates inputs and starts dumping in background thread."""
        if self.is_dumping:
            return

        selected_reader = self.reader_combobox.get()
        if not selected_reader or selected_reader == "Ридеры не найдены":
            messagebox.showwarning("Ошибка", "Считыватель не выбран или не подключен.")
            return

        pin = self.pin_entry.get().strip()

        self.is_dumping = True
        self.dump_btn.config(state=tk.DISABLED)
        self.refresh_btn.config(state=tk.DISABLED)
        self.progress_bar["value"] = 0
        self.status_lbl.config(text="Подключение к карте...", foreground="#000000")

        threading.Thread(
            target=self._dump_worker,
            args=(selected_reader, pin),
            daemon=True
        ).start()

    def _dump_worker(self, reader_name: str, pin: str):
        try:
            logger.info("=" * 40)
            logger.info(f"Начало операции дампа карты. Ридер: {reader_name}")

            ok = self.reader.connect(reader_name)
            if not ok:
                raise RuntimeError("Не удалось подключиться к смарт-карте. Убедитесь, что карта вставлена чипом вперед/вверх.")

            def on_progress(percent: float, text: str, count: int):
                self.after(0, lambda: self._update_progress(percent, text))

            ef_map, sig_map = self.reader.dump_all_efs(pin_str=pin, progress_callback=on_progress)

            if not ef_map:
                raise RuntimeError("Ни один файл (EF) с карты не был прочитан.")

            # Save DDD file with 5-byte TLV blocks and digital signatures
            out_file, total_bytes = save_ddd_file(ef_map, self.dumps_dir, ef_signatures_map=sig_map)
            
            # Extract card info
            info = {}
            if 0x0520 in ef_map:
                info = parse_card_identification(ef_map[0x0520])

            summary_msg = (
                f"Дамп успешно сохранен!\n\n"
                f"Файл: {os.path.basename(out_file)}\n"
                f"Размер: {total_bytes} байт\n"
                f"Прочитано секций (EF): {len(ef_map)} (подписей: {len(sig_map)})\n"
            )
            if info.get("holder_surname") or info.get("holder_name"):
                summary_msg += f"Владелец: {info.get('holder_surname', '')} {info.get('holder_name', '')}\n"
            if info.get("card_number"):
                summary_msg += f"Номер карты: {info.get('card_number')}\n"

            logger.info(summary_msg.replace("\n\n", " ").replace("\n", ", "))

            self.after(0, lambda: self._on_dump_success(out_file, summary_msg))

        except Exception as e:
            logger.error(f"Ошибка в процессе дампа: {e}", exc_info=True)
            self.after(0, lambda: self._on_dump_error(str(e)))
        finally:
            self.reader.disconnect()
            self.after(0, self._on_dump_finished)

    def _update_progress(self, percent: float, text: str):
        self.progress_bar["value"] = percent
        self.status_lbl.config(text=text, foreground="#000000")

    def _on_dump_success(self, file_path: str, msg: str):
        self.status_lbl.config(text=f"Успешно сохранен: {os.path.basename(file_path)}", foreground="#008800")
        resp = messagebox.askyesno(
            "Дамп сохранен успешно",
            f"{msg}\nОткрыть просмотрщик данных карты прямо сейчас?"
        )
        if resp:
            self.open_viewer(file_path)

    def open_viewer(self, file_path: Optional[str] = None):
        """Opens DDD viewer window for specified file or prompts to choose one."""
        if not file_path:
            from tkinter import filedialog
            file_path = filedialog.askopenfilename(
                parent=self,
                title="Выберите тахографический файл для просмотра",
                initialdir=self.dumps_dir,
                filetypes=[("Файлы тахографа (*.ddd, *.tgd, *.esm)", "*.ddd *.tgd *.esm *.c1b *.v1b"), ("Все файлы (*.*)", "*.*")]
            )
        if file_path and os.path.exists(file_path):
            DddViewerWindow(self, initial_file=file_path)

    def _on_dump_error(self, err_text: str):
        self.status_lbl.config(text=f"Ошибка: {err_text}", foreground="#cc0000")
        messagebox.showerror(
            "Ошибка чтения",
            f"Произошла ошибка при считывании карты:\n\n{err_text}\n\nПодробности записаны в лог-файл: taho_debug.log"
        )

    def _on_dump_finished(self):
        self.is_dumping = False
        self.dump_btn.config(state=tk.NORMAL)
        self.refresh_btn.config(state=tk.NORMAL)

def run_app():
    app = TahoDumperApp()
    app.mainloop()

if __name__ == "__main__":
    run_app()
