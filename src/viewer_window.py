from __future__ import annotations

"""
DDD File Viewer Window
Interactive GUI component for inspecting parsed tachograph .DDD files.
Provides specialized views for Workshop Card calibrations and Driver Card activity.
"""

import os
import csv
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Optional

from .ddd_parser import ParsedDDD, load_ddd_file
from .logger import logger

class DddViewerWindow(tk.Toplevel):
    def __init__(self, parent: tk.Tk, initial_file: Optional[str] = None):
        super().__init__(parent)
        self.title("Просмотр данных тахографического файла (.DDD)")
        self.geometry("980x680")
        self.minsize(850, 550)

        self.current_parsed: Optional[ParsedDDD] = None
        self.all_calibrations: list = []

        self._build_ui()

        if initial_file and os.path.exists(initial_file):
            self.load_file(initial_file)

    def _build_ui(self):
        # 1. Top Bar
        top_bar = ttk.Frame(self, padding=(12, 8))
        top_bar.pack(fill=tk.X)

        self.file_lbl = ttk.Label(
            top_bar,
            text="Файл не выбран",
            font=("Segoe UI", 11, "bold")
        )
        self.file_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        open_btn = ttk.Button(top_bar, text="📂 Открыть другой .DDD...", command=self._on_browse_file)
        open_btn.pack(side=tk.RIGHT, padx=(6, 0))

        # 2. Notebook
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 10))

        # Tab 1: Overview
        self.tab_overview = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(self.tab_overview, text="📋 Данные карты")
        self._build_overview_tab(self.tab_overview)

        # Tab 2: Workshop Calibrations
        self.tab_calibs = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(self.tab_calibs, text="🔧 Протоколы калибровок")
        self._build_calibrations_tab(self.tab_calibs)

        # Tab 3: Driver Vehicles Used
        self.tab_vehicles = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(self.tab_vehicles, text="🚚 Использование ТС")
        self._build_vehicles_tab(self.tab_vehicles)

        # Tab 4: Raw EF Blocks
        self.tab_blocks = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(self.tab_blocks, text="🔐 Секции и Подписи")
        self._build_blocks_tab(self.tab_blocks)

    def _build_overview_tab(self, parent: ttk.Frame):
        scroll_canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=scroll_canvas.yview)
        inner_frame = ttk.Frame(scroll_canvas)

        inner_frame.bind(
            "<Configure>",
            lambda e: scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))
        )
        scroll_canvas.create_window((0, 0), window=inner_frame, anchor="nw")
        scroll_canvas.configure(xscrollcommand=None, yscrollcommand=scrollbar.set)

        scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Card Info Frame
        c_frame = ttk.LabelFrame(inner_frame, text=" Сведения о карте ", padding=10)
        c_frame.pack(fill=tk.X, expand=True, pady=(0, 10))

        self.ov_type_val = self._add_row(c_frame, 0, "Тип карты:", "-")
        self.ov_cardnum_val = self._add_row(c_frame, 1, "Номер карты:", "-")
        self.ov_nation_val = self._add_row(c_frame, 2, "Страна выдачи:", "-")
        self.ov_auth_val = self._add_row(c_frame, 3, "Орган выдачи:", "-")
        self.ov_valid_val = self._add_row(c_frame, 4, "Срок действия:", "-")

        # Holder Info Frame
        h_frame = ttk.LabelFrame(inner_frame, text=" Владелец / Мастерская ", padding=10)
        h_frame.pack(fill=tk.X, expand=True, pady=(0, 10))

        self.ov_holder_val = self._add_row(h_frame, 0, "Держатель карты:", "-")
        self.ov_extra_val1 = self._add_row(h_frame, 1, "Организация / ВУ:", "-")
        self.ov_extra_val2 = self._add_row(h_frame, 2, "Адрес / Дата рожд.:", "-")
        self.ov_lang_val = self._add_row(h_frame, 3, "Язык интерфейса:", "-")

        # Summary Statistics Frame
        s_frame = ttk.LabelFrame(inner_frame, text=" Содержимое дампа ", padding=10)
        s_frame.pack(fill=tk.X, expand=True)

        self.ov_stats_val = self._add_row(s_frame, 0, "Сводка данных:", "-")

    def _add_row(self, parent: ttk.Frame, row: int, label_text: str, default_val: str) -> ttk.Label:
        lbl_title = ttk.Label(parent, text=label_text, font=("Segoe UI", 9, "bold"), width=22)
        lbl_title.grid(row=row, column=0, sticky=tk.W, pady=3)
        lbl_val = ttk.Label(parent, text=default_val, font=("Segoe UI", 9))
        lbl_val.grid(row=row, column=1, sticky=tk.W, pady=3)
        return lbl_val

    def _build_calibrations_tab(self, parent: ttk.Frame):
        # Search & Export Bar
        bar = ttk.Frame(parent)
        bar.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(bar, text="🔍 Поиск (VIN, номер, модель):").pack(side=tk.LEFT, padx=(0, 6))
        self.calib_search_var = tk.StringVar()
        self.calib_search_var.trace_add("write", lambda *args: self._filter_calibrations())
        search_entry = ttk.Entry(bar, textvariable=self.calib_search_var, width=30)
        search_entry.pack(side=tk.LEFT, padx=(0, 10))

        self.calib_count_lbl = ttk.Label(bar, text="Записей: 0", font=("Segoe UI", 9, "bold"))
        self.calib_count_lbl.pack(side=tk.LEFT)

        csv_btn = ttk.Button(bar, text="💾 Экспорт в CSV...", command=self._export_calibrations_csv)
        csv_btn.pack(side=tk.RIGHT)

        # Treeview Table
        cols = ("idx", "date", "vin", "plate", "odo", "vu_part", "wk", "tyre", "next_date", "purpose")
        self.calib_tree = ttk.Treeview(parent, columns=cols, show="headings", selectmode="browse")
        
        self.calib_tree.heading("idx", text="№")
        self.calib_tree.heading("date", text="Дата калибровки")
        self.calib_tree.heading("vin", text="VIN")
        self.calib_tree.heading("plate", text="Госномер")
        self.calib_tree.heading("odo", text="Одометр (км)")
        self.calib_tree.heading("vu_part", text="Модель тахографа")
        self.calib_tree.heading("wk", text="W / K")
        self.calib_tree.heading("tyre", text="Размер шин")
        self.calib_tree.heading("next_date", text="След. поверка")
        self.calib_tree.heading("purpose", text="Цель")

        self.calib_tree.column("idx", width=40, anchor=tk.CENTER)
        self.calib_tree.column("date", width=110, anchor=tk.W)
        self.calib_tree.column("vin", width=140, anchor=tk.W)
        self.calib_tree.column("plate", width=90, anchor=tk.CENTER)
        self.calib_tree.column("odo", width=90, anchor=tk.E)
        self.calib_tree.column("vu_part", width=140, anchor=tk.W)
        self.calib_tree.column("wk", width=90, anchor=tk.CENTER)
        self.calib_tree.column("tyre", width=110, anchor=tk.W)
        self.calib_tree.column("next_date", width=110, anchor=tk.W)
        self.calib_tree.column("purpose", width=150, anchor=tk.W)

        tree_scroll_y = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.calib_tree.yview)
        tree_scroll_x = ttk.Scrollbar(parent, orient=tk.HORIZONTAL, command=self.calib_tree.xview)
        self.calib_tree.configure(yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)

        self.calib_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_vehicles_tab(self, parent: ttk.Frame):
        cols = ("idx", "plate", "nation", "odo_b", "odo_e", "km", "first", "last")
        self.veh_tree = ttk.Treeview(parent, columns=cols, show="headings", selectmode="browse")

        self.veh_tree.heading("idx", text="№")
        self.veh_tree.heading("plate", text="Госномер")
        self.veh_tree.heading("nation", text="Страна")
        self.veh_tree.heading("odo_b", text="Одометр нач.")
        self.veh_tree.heading("odo_e", text="Одометр кон.")
        self.veh_tree.heading("km", text="Пробег (км)")
        self.veh_tree.heading("first", text="Первое использование")
        self.veh_tree.heading("last", text="Последнее использование")

        self.veh_tree.column("idx", width=40, anchor=tk.CENTER)
        self.veh_tree.column("plate", width=110, anchor=tk.CENTER)
        self.veh_tree.column("nation", width=110, anchor=tk.W)
        self.veh_tree.column("odo_b", width=95, anchor=tk.E)
        self.veh_tree.column("odo_e", width=95, anchor=tk.E)
        self.veh_tree.column("km", width=85, anchor=tk.E)
        self.veh_tree.column("first", width=120, anchor=tk.W)
        self.veh_tree.column("last", width=120, anchor=tk.W)

        v_scroll_y = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.veh_tree.yview)
        self.veh_tree.configure(yscrollcommand=v_scroll_y.set)

        self.veh_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_blocks_tab(self, parent: ttk.Frame):
        cols = ("fid", "kind", "length", "offset", "desc")
        self.blocks_tree = ttk.Treeview(parent, columns=cols, show="headings", selectmode="browse")

        self.blocks_tree.heading("fid", text="Тег (FID)")
        self.blocks_tree.heading("kind", text="Тип блока")
        self.blocks_tree.heading("length", text="Размер (байт)")
        self.blocks_tree.heading("offset", text="Смещение")
        self.blocks_tree.heading("desc", text="Описание файла")

        self.blocks_tree.column("fid", width=80, anchor=tk.CENTER)
        self.blocks_tree.column("kind", width=100, anchor=tk.CENTER)
        self.blocks_tree.column("length", width=95, anchor=tk.E)
        self.blocks_tree.column("offset", width=95, anchor=tk.E)
        self.blocks_tree.column("desc", width=380, anchor=tk.W)

        b_scroll = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.blocks_tree.yview)
        self.blocks_tree.configure(yscrollcommand=b_scroll.set)

        self.blocks_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        b_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _on_browse_file(self):
        f = filedialog.askopenfilename(
            parent=self,
            title="Выберите тахографический файл",
            filetypes=[("Файлы тахографа (*.ddd, *.tgd, *.esm)", "*.ddd *.tgd *.esm *.c1b *.v1b"), ("Все файлы (*.*)", "*.*")]
        )
        if f:
            self.load_file(f)

    def load_file(self, filepath: str):
        try:
            parsed = load_ddd_file(filepath)
            self.current_parsed = parsed
            self.file_lbl.config(text=f"Файл: {os.path.basename(filepath)} ({parsed.file_size:,} байт)")

            # Populate Overview
            self.ov_type_val.config(text=parsed.card_type_name)
            self.ov_cardnum_val.config(text=parsed.card_number or "-")
            self.ov_nation_val.config(text=parsed.member_state_name)
            self.ov_auth_val.config(text=parsed.issuing_authority or "-")
            self.ov_valid_val.config(text=f"{parsed.validity_begin}  —  {parsed.validity_end}")

            full_name = f"{parsed.holder_surname} {parsed.holder_firstnames}".strip()
            self.ov_holder_val.config(text=full_name or "-")

            if parsed.card_type_id == 2:  # Workshop
                self.ov_extra_val1.config(text=f"Мастерская: {parsed.workshop_name or '-'}")
                self.ov_extra_val2.config(text=f"Адрес: {parsed.workshop_address or '-'}")
            else:  # Driver
                dl = f"{parsed.driving_licence_num} ({parsed.driving_licence_authority})".strip()
                self.ov_extra_val1.config(text=f"Водит. удост.: {dl or '-'}")
                self.ov_extra_val2.config(text=f"Дата рождения: {parsed.birth_date or '-'}")

            self.ov_lang_val.config(text=parsed.preferred_language or "-")

            stats_text = (
                f"Всего секций (EF): {len(parsed.data_blocks)} | Подписей: {len(parsed.signature_blocks)}\n"
            )
            if parsed.calibrations:
                stats_text += f"Калибровок в базе карты: {len(parsed.calibrations)}\n"
            if parsed.vehicles_used:
                stats_text += f"Записей использования ТС: {len(parsed.vehicles_used)}\n"
            if parsed.places:
                stats_text += f"Записей мест начала/конца смен: {len(parsed.places)}\n"
            self.ov_stats_val.config(text=stats_text.strip())

            # Populate Calibrations
            self.all_calibrations = parsed.calibrations
            self._filter_calibrations()

            # Populate Vehicles Used
            for row in self.veh_tree.get_children():
                self.veh_tree.delete(row)
            for v in parsed.vehicles_used:
                self.veh_tree.insert("", tk.END, values=(
                    v["index"], v["plate"], v["nation"],
                    f"{v['odo_begin']:,}", f"{v['odo_end']:,}", f"{v['km_driven']:,}",
                    v["first_use"], v["last_use"]
                ))

            # Populate Blocks
            for row in self.blocks_tree.get_children():
                self.blocks_tree.delete(row)
            
            fid_names = {
                0x0002: "EF_ICC (Идентификация карты)",
                0x0005: "EF_IC (Идентификация чипа)",
                0x0501: "EF_Application_Identification (Тип карты и структура)",
                0xC100: "EF_Card_Certificate (Сертификат карты)",
                0xC108: "EF_CA_Certificate (Сертификат государства)",
                0x0520: "EF_Identification (Данные карты и владельца)",
                0x0509: "EF_Card_Download (Калибровки с последней выгрузки)",
                0x050A: "EF_Calibration_Data (База протоколов калибровок)",
                0x050B: "EF_Sensor_Installation_Data (Сенсор движения)",
                0x050E: "EF_Card_Download (Дата последней выгрузки водителя)",
                0x0521: "EF_Driving_Licence_Info (Водительское удостоверение)",
                0x0502: "EF_Events_Data (События тахографа)",
                0x0503: "EF_Faults_Data (Неисправности)",
                0x0504: "EF_Driver_Activity_Data (Деятельность водителя)",
                0x0505: "EF_Vehicles_Used (Использованные ТС)",
                0x0506: "EF_Places (Места начала и конца смен)",
                0x0507: "EF_Current_Usage (Текущая сессия)",
                0x0508: "EF_Control_Activity_Data (Контрольные проверки)",
                0x0522: "EF_Specific_Conditions (Специфические условия)",
            }

            for b in parsed.block_records:
                desc = fid_names.get(b["fid"], "Пользовательский файл EF")
                self.blocks_tree.insert("", tk.END, values=(
                    b["fid_hex"], b["kind"], f"{b['length']:,}", f"{b['offset']:,}", desc
                ))

            # Switch to calibrations tab automatically if workshop card
            if parsed.card_type_id == 2 and parsed.calibrations:
                self.notebook.select(self.tab_calibs)
            elif parsed.vehicles_used:
                self.notebook.select(self.tab_vehicles)
            else:
                self.notebook.select(self.tab_overview)

        except Exception as e:
            logger.error(f"Ошибка загрузки файла {filepath}: {e}", exc_info=True)
            messagebox.showerror("Ошибка", f"Не удалось прочитать файл:\n{e}")

    def _filter_calibrations(self):
        query = self.calib_search_var.get().strip().lower()
        for row in self.calib_tree.get_children():
            self.calib_tree.delete(row)

        matching = 0
        for c in self.all_calibrations:
            searchable = f"{c['vin']} {c['plate']} {c['vu_part']} {c['purpose']}".lower()
            if not query or query in searchable:
                matching += 1
                self.calib_tree.insert("", tk.END, values=(
                    c["index"], c["date"], c["vin"], c["plate"],
                    f"{c['odo']:,}", c["vu_part"], f"{c['w']}/{c['k']}",
                    c["tyre"], c["next_date"], c["purpose"]
                ))
        self.calib_count_lbl.config(text=f"Записей: {matching} из {len(self.all_calibrations)}")

    def _export_calibrations_csv(self):
        if not self.all_calibrations:
            messagebox.showwarning("Экспорт", "Нет записей для экспорта.")
            return

        out_path = filedialog.asksaveasfilename(
            parent=self,
            title="Экспорт калибровок в CSV",
            defaultextension=".csv",
            filetypes=[("CSV Таблица (*.csv)", "*.csv"), ("Все файлы (*.*)", "*.*")]
        )
        if not out_path:
            return

        try:
            with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow([
                    "№", "Дата калибровки", "VIN", "Госномер", "Страна",
                    "Одометр (км)", "Модель тахографа (Part No)", "Серийный номер",
                    "w", "k", "l (окружность)", "Размер шин", "Ограничитель скорости",
                    "След. поверка", "Цель калибровки"
                ])
                for c in self.all_calibrations:
                    writer.writerow([
                        c["index"], c["date"], c["vin"], c["plate"], c["nation"],
                        c["odo"], c["vu_part"], c["vu_serial"],
                        c["w"], c["k"], c["l"], c["tyre"], c["speed"],
                        c["next_date"], c["purpose"]
                    ])
            messagebox.showinfo("Экспорт завершен", f"Успешно сохранено {len(self.all_calibrations)} записей в:\n{out_path}")
        except Exception as e:
            messagebox.showerror("Ошибка экспорта", f"Не удалось сохранить CSV:\n{e}")
