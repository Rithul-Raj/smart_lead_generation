"""
Module 1 (enhanced): User Input Collection — GUI Form
------------------------------------------------------
Smart Lead Generation AI Model | Detagenix Internship Project

Provides a clean desktop window (built with Python's built-in tkinter)
that collects the three search parameters from the user before the
pipeline starts:

    • Number of Leads  (integer spinner, 1–200)
    • Location         (free text, e.g. "Bangalore, India")
    • Industry         (free text + dropdown suggestions)

Usage
-----
    from input_form import LeadInputForm

    form = LeadInputForm()
    params = form.run()   # blocks until user clicks Start or closes window

    if params is None:
        print("User cancelled.")
    else:
        print(params)
        # → {"num_leads": 10, "location": "Bangalore, India", "industry": "IT"}

No third-party packages needed — only tkinter (ships with Python).
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Dict, Any

# ── Suggested industries shown in the dropdown ───────────────────────────────
INDUSTRY_SUGGESTIONS = [
    "Information Technology",
    "Software Development",
    "Healthcare",
    "Finance & Banking",
    "Education",
    "E-commerce / Retail",
    "Manufacturing",
    "Real Estate",
    "Logistics & Supply Chain",
    "Media & Entertainment",
    "Food & Beverage",
    "Consulting",
    "Telecommunications",
    "Automotive",
    "Construction",
]

# ── Color / font palette (Detagenix brand feel) ──────────────────────────────
BG_DARK        = "#0f1117"   # main background
BG_CARD        = "#1a1d27"   # card / panel background
ACCENT         = "#4f8ef7"   # primary blue
ACCENT_HOVER   = "#3a7de0"
SUCCESS        = "#22c55e"   # start button green
SUCCESS_HOVER  = "#16a34a"
DANGER         = "#ef4444"   # cancel red
TEXT_PRIMARY   = "#f1f5f9"
TEXT_SECONDARY = "#94a3b8"
TEXT_LABEL     = "#cbd5e1"
BORDER         = "#2d3147"
INPUT_BG       = "#252837"
INPUT_FG       = "#f1f5f9"

FONT_TITLE     = ("Segoe UI", 17, "bold")
FONT_SUBTITLE  = ("Segoe UI", 10)
FONT_LABEL     = ("Segoe UI", 10, "bold")
FONT_INPUT     = ("Segoe UI", 11)
FONT_BTN       = ("Segoe UI", 11, "bold")
FONT_FOOTER    = ("Segoe UI", 9)


class LeadInputForm:
    """
    A modal tkinter window that collects search parameters from the user.

    Call  .run()  to open it; it blocks until the user clicks Start Search
    or closes the window, then returns the collected parameters (or None).
    """

    def __init__(self):
        self._result: Optional[Dict[str, Any]] = None

    # ── public entry point ────────────────────────────────────────────────────

    def run(self) -> Optional[Dict[str, Any]]:
        """
        Open the input form and wait for the user to submit or cancel.

        Returns:
            dict  with keys num_leads (int), location (str), industry (str)
                  if the user clicked Start Search with valid inputs.
            None  if the user clicked Cancel or closed the window.
        """
        root = tk.Tk()
        self._build_ui(root)
        root.mainloop()
        return self._result

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self, root: tk.Tk) -> None:
        root.title("Smart Lead Generation — Detagenix")
        root.configure(bg=BG_DARK)
        root.resizable(False, False)

        # Centre on screen
        w, h = 520, 560
        root.geometry(f"{w}x{h}")
        root.update_idletasks()
        x = (root.winfo_screenwidth()  - w) // 2
        y = (root.winfo_screenheight() - h) // 2
        root.geometry(f"{w}x{h}+{x}+{y}")

        # ── header bar ────────────────────────────────────────────────────────
        header = tk.Frame(root, bg=ACCENT, height=6)
        header.pack(fill="x")

        title_frame = tk.Frame(root, bg=BG_DARK, pady=22)
        title_frame.pack(fill="x", padx=30)

        tk.Label(
            title_frame,
            text="Smart Lead Generation",
            font=FONT_TITLE,
            fg=TEXT_PRIMARY,
            bg=BG_DARK,
        ).pack(anchor="w")

        tk.Label(
            title_frame,
            text="Fill in the details below to start discovering business leads.",
            font=FONT_SUBTITLE,
            fg=TEXT_SECONDARY,
            bg=BG_DARK,
        ).pack(anchor="w", pady=(4, 0))

        # ── card container ────────────────────────────────────────────────────
        card = tk.Frame(root, bg=BG_CARD, bd=0, relief="flat")
        card.pack(fill="both", padx=28, pady=(0, 10))

        # Thin top border line on the card
        tk.Frame(card, bg=ACCENT, height=2).pack(fill="x")

        inner = tk.Frame(card, bg=BG_CARD, padx=24, pady=20)
        inner.pack(fill="both", expand=True)

        # ── Number of Leads ───────────────────────────────────────────────────
        self._make_label(inner, "Number of Leads", "How many companies to find")

        leads_row = tk.Frame(inner, bg=BG_CARD)
        leads_row.pack(fill="x", pady=(4, 16))

        self._leads_var = tk.IntVar(value=10)
        leads_spin = tk.Spinbox(
            leads_row,
            from_=1,
            to=200,
            textvariable=self._leads_var,
            font=FONT_INPUT,
            bg=INPUT_BG,
            fg=INPUT_FG,
            insertbackground=TEXT_PRIMARY,
            relief="flat",
            bd=0,
            width=10,
            buttonbackground=BG_CARD,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
        )
        leads_spin.pack(side="left", ipady=6, ipadx=4)

        tk.Label(
            leads_row,
            text="  (max 200 per search)",
            font=FONT_FOOTER,
            fg=TEXT_SECONDARY,
            bg=BG_CARD,
        ).pack(side="left", pady=2)

        # ── Location ──────────────────────────────────────────────────────────
        self._make_label(inner, "Location", "City, state, or country  (optional — leave blank to search globally)")

        self._location_var = tk.StringVar()
        loc_entry = self._make_entry(inner, self._location_var, "e.g. Mumbai, India")
        loc_entry.pack(fill="x", pady=(4, 16), ipady=7)

        # ── Industry ──────────────────────────────────────────────────────────
        self._make_label(inner, "Industry", "Business sector to search in  (required — type or select from list)")

        self._industry_var = tk.StringVar()
        industry_combo = ttk.Combobox(
            inner,
            textvariable=self._industry_var,
            values=INDUSTRY_SUGGESTIONS,
            font=FONT_INPUT,
            state="normal",   # editable, not just a fixed dropdown
        )
        industry_combo.set("")  # intentionally blank — user must choose/type
        self._style_combobox(industry_combo)
        industry_combo.pack(fill="x", pady=(4, 6), ipady=6)

        tk.Label(
            inner,
            text="  You can type a custom industry if it's not in the list.",
            font=FONT_FOOTER,
            fg=TEXT_SECONDARY,
            bg=BG_CARD,
        ).pack(anchor="w")

        # ── status message area ───────────────────────────────────────────────
        self._status_var = tk.StringVar()
        self._status_label = tk.Label(
            inner,
            textvariable=self._status_var,
            font=("Segoe UI", 9, "italic"),
            fg=DANGER,
            bg=BG_CARD,
            wraplength=420,
            justify="left",
        )
        self._status_label.pack(anchor="w", pady=(10, 0))

        # ── buttons ───────────────────────────────────────────────────────────
        btn_frame = tk.Frame(root, bg=BG_DARK, padx=28, pady=12)
        btn_frame.pack(fill="x")

        cancel_btn = self._make_button(
            btn_frame,
            text="Cancel",
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            hover_bg="#2a2d3a",
            command=lambda: self._on_cancel(root),
        )
        cancel_btn.pack(side="right", padx=(8, 0))

        start_btn = self._make_button(
            btn_frame,
            text="Start Search",
            bg=SUCCESS,
            fg="#fff",
            hover_bg=SUCCESS_HOVER,
            command=lambda: self._on_submit(root),
        )
        start_btn.pack(side="right")

        # ── footer ────────────────────────────────────────────────────────────
        tk.Label(
            root,
            text="Detagenix  ·  Smart Lead Generation AI Model  ·  Internship Project",
            font=FONT_FOOTER,
            fg=TEXT_SECONDARY,
            bg=BG_DARK,
        ).pack(pady=(0, 12))

        # Bind Enter key to submit
        root.bind("<Return>", lambda e: self._on_submit(root))
        root.protocol("WM_DELETE_WINDOW", lambda: self._on_cancel(root))

        self._root = root

    # ── widget factory helpers ────────────────────────────────────────────────

    def _make_label(self, parent, title: str, subtitle: str) -> None:
        tk.Label(
            parent, text=title, font=FONT_LABEL, fg=TEXT_LABEL, bg=BG_CARD
        ).pack(anchor="w")
        tk.Label(
            parent, text=subtitle, font=FONT_FOOTER, fg=TEXT_SECONDARY, bg=BG_CARD
        ).pack(anchor="w", pady=(1, 0))

    def _make_entry(self, parent, var: tk.StringVar, placeholder: str) -> tk.Entry:
        entry = tk.Entry(
            parent,
            textvariable=var,
            font=FONT_INPUT,
            bg=INPUT_BG,
            fg=INPUT_FG,
            insertbackground=TEXT_PRIMARY,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
        )
        # Placeholder behaviour
        if placeholder:
            entry.insert(0, placeholder)
            entry.config(fg=TEXT_SECONDARY)

            def on_focus_in(e):
                if entry.get() == placeholder:
                    entry.delete(0, "end")
                    entry.config(fg=INPUT_FG)

            def on_focus_out(e):
                if not entry.get():
                    entry.insert(0, placeholder)
                    entry.config(fg=TEXT_SECONDARY)

            entry.bind("<FocusIn>",  on_focus_in)
            entry.bind("<FocusOut>", on_focus_out)

        return entry

    def _make_button(
        self,
        parent,
        text: str,
        bg: str,
        fg: str,
        hover_bg: str,
        command,
        width: int = 18,
    ) -> tk.Button:
        btn = tk.Button(
            parent,
            text=text,
            font=FONT_BTN,
            bg=bg,
            fg=fg,
            activebackground=hover_bg,
            activeforeground=fg,
            relief="flat",
            bd=0,
            padx=16,
            pady=9,
            cursor="hand2",
            command=command,
            width=width,
        )
        btn.bind("<Enter>", lambda e: btn.config(bg=hover_bg))
        btn.bind("<Leave>", lambda e: btn.config(bg=bg))
        return btn

    @staticmethod
    def _style_combobox(combo: ttk.Combobox) -> None:
        """Apply dark styling to the combobox using ttk style overrides."""
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "TCombobox",
            fieldbackground=INPUT_BG,
            background=INPUT_BG,
            foreground=INPUT_FG,
            arrowcolor=TEXT_SECONDARY,
            bordercolor=BORDER,
            darkcolor=INPUT_BG,
            lightcolor=INPUT_BG,
            selectbackground=ACCENT,
            selectforeground="#fff",
        )
        style.map("TCombobox", fieldbackground=[("readonly", INPUT_BG)])

    # ── event handlers ────────────────────────────────────────────────────────

    def _on_submit(self, root: tk.Tk) -> None:
        # Validate leads count
        try:
            num_leads = int(self._leads_var.get())
            if num_leads < 1 or num_leads > 200:
                raise ValueError
        except (ValueError, tk.TclError):
            self._status_var.set("Please enter a valid number of leads (1-200).")
            return

        # Location is optional — empty string is allowed
        location = self._location_var.get().strip()
        placeholder_loc = "e.g. Mumbai, India"
        if location == placeholder_loc:
            location = ""   # treat placeholder text as no input

        # Validate industry (mandatory)
        industry = self._industry_var.get().strip()
        if not industry:
            self._status_var.set("Industry is required. Please type or select an industry from the list.")
            return

        self._result = {
            "num_leads": num_leads,
            "location":  location,
            "industry":  industry,
        }
        root.destroy()

    def _on_cancel(self, root: tk.Tk) -> None:
        self._result = None
        root.destroy()


# ── Standalone test ────────────────────────────────────────────────────────
if __name__ == "__main__":
    form   = LeadInputForm()
    params = form.run()

    if params is None:
        print("Cancelled by user.")
    else:
        print("Input collected:")
        for k, v in params.items():
            print(f"  {k}: {v}")
