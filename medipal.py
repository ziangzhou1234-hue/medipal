#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MediPal — A tiny CLI to keep meds on time and log symptoms
(Colored output + simple symptom analysis + correct delete mapping)

Author: Your Name (Student ID)
Course: COMP9001 Final Project

Standard library only. JSON persistence.

Features
- Manage drugs (name, dosage, times per day, start/end dates, notes)
- Show daily schedule for any date
- Mark a scheduled dose as TAKEN or MISSED
- Log symptoms with intensity 1–5
- Weekly adherence % and ASCII charts (colored)
- Export dose & symptom logs to CSV
"""

from __future__ import annotations
import json
import os
import sys
import csv
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple
from datetime import datetime, date, time, timedelta

DATA_FILE = "medipal_data.json"
DATE_FMT = "%Y-%m-%d"
TIME_FMT = "%H:%M"

# --------------------------- ANSI Color Helper ---------------------------

class Ansi:
    RESET = "\033[0m"
    BOLD  = "\033[1m"
    FG = {
        "red": "\033[31m", "green": "\033[32m", "yellow": "\033[33m",
        "blue": "\033[34m", "magenta": "\033[35m", "cyan": "\033[36m",
        "white": "\033[37m", "gray": "\033[90m"
    }

def color(s: str, fg: Optional[str] = None, bold: bool = False) -> str:
    """Wrap text with ANSI color/bold if terminal supports it. Set env NOPAINT=1 to disable."""
    if not sys.stdout.isatty() or os.environ.get("NOPAINT") == "1":
        return s
    parts = []
    if bold:
        parts.append(Ansi.BOLD)
    if fg:
        parts.append(Ansi.FG.get(fg, ""))
    return "".join(parts) + s + Ansi.RESET

def ok(msg: str):   print(color(msg, "green"))
def warn(msg: str): print(color(msg, "yellow"))
def err(msg: str):  print(color(msg, "red", True))

# ----------------------------- Models -----------------------------

@dataclass
class Drug:
    name: str
    dosage: str                     # e.g., "500mg"
    times: List[str]                # HH:MM list, e.g., ["08:00","20:00"]
    start_date: str                 # YYYY-MM-DD
    end_date: Optional[str] = None  # None for ongoing
    notes: Optional[str] = None

    def active_on(self, d: date) -> bool:
        sd = datetime.strptime(self.start_date, DATE_FMT).date()
        if self.end_date:
            ed = datetime.strptime(self.end_date, DATE_FMT).date()
            return sd <= d <= ed
        return sd <= d

    def times_as_time(self) -> List[time]:
        out = []
        for t in self.times:
            try:
                out.append(datetime.strptime(t, TIME_FMT).time())
            except Exception:
                continue
        return sorted(out)

@dataclass
class DoseLog:
    date_str: str                  # YYYY-MM-DD
    time_str: str                  # HH:MM
    drug_name: str
    status: str                    # "TAKEN" | "MISSED"
    note: Optional[str] = None

@dataclass
class SymptomLog:
    date_str: str                  # YYYY-MM-DD
    symptom: str                   # e.g., "headache"
    intensity: int                 # 1..5
    note: Optional[str] = None

# ----------------------------- Store -----------------------------

class MediPal:
    def __init__(self):
        self.drugs: List[Drug] = []
        self.dose_logs: List[DoseLog] = []
        self.symptoms: List[SymptomLog] = []

    # ---- CRUD Drugs ----
    def add_drug(self, drug: Drug):
        self.drugs.append(drug)

    def remove_drug(self, idx: int) -> Optional[Drug]:
        if 0 <= idx < len(self.drugs):
            return self.drugs.pop(idx)
        return None

    def list_drugs(self) -> List[Drug]:
        return sorted(self.drugs, key=lambda d: d.name.lower())

    # ---- Scheduling ----
    def daily_schedule(self, d: date) -> List[Tuple[Drug, time]]:
        sched: List[Tuple[Drug, time]] = []
        for drug in self.drugs:
            if drug.active_on(d):
                for t in drug.times_as_time():
                    sched.append((drug, t))
        return sorted(sched, key=lambda x: (x[1], x[0].name.lower()))

    def _log_key(self, date_str: str, time_str: str, drug_name: str) -> Tuple[str, str, str]:
        return (date_str, time_str, drug_name.lower())

    def get_dose_status(self, d: date, t: time, drug_name: str) -> Optional[str]:
        ds, ts = d.isoformat(), t.strftime(TIME_FMT)
        for log in self.dose_logs:
            if (log.date_str, log.time_str, log.drug_name.lower()) == self._log_key(ds, ts, drug_name):
                return log.status
        return None

    def mark_dose(self, d: date, t: time, drug_name: str, status: str, note: Optional[str] = None):
        if status not in ("TAKEN", "MISSED"):
            raise ValueError("status must be TAKEN or MISSED")
        ds, ts = d.isoformat(), t.strftime(TIME_FMT)
        for i, log in enumerate(self.dose_logs):
            if (log.date_str, log.time_str, log.drug_name.lower()) == self._log_key(ds, ts, drug_name):
                self.dose_logs[i] = DoseLog(ds, ts, drug_name, status, note)
                return
        self.dose_logs.append(DoseLog(ds, ts, drug_name, status, note))

    # ---- Symptoms ----
    def add_symptom(self, sym: SymptomLog):
        if not (1 <= sym.intensity <= 5):
            raise ValueError("Intensity must be 1..5")
        self.symptoms.append(sym)

    # ---- Stats ----
    def adherence_last_7_days(self) -> Tuple[int, int, float]:
        today = date.today()
        taken = expected = 0
        for n in range(7):
            d = today - timedelta(days=n)
            sched = self.daily_schedule(d)
            expected += len(sched)
            for drug, t in sched:
                if self.get_dose_status(d, t, drug.name) == "TAKEN":
                    taken += 1
        percent = (taken / expected * 100) if expected else 100.0
        return taken, expected, round(percent, 1)

    def ascii_weekly_adherence(self) -> str:
        """Bar per day for % taken, colored by threshold."""
        today = date.today()
        lines = [color("Adherence last 7 days (today first)", "magenta", True)]
        for n in range(7):
            d = today - timedelta(days=n)
            sched = self.daily_schedule(d)
            if not sched:
                pct = 100
            else:
                hits = sum(1 for (drug, t) in sched if self.get_dose_status(d, t, drug.name) == "TAKEN")
                pct = int(round(hits / len(sched) * 100))
            bar = "#" * (pct // 5)  # 0..20
            fg = "green" if pct >= 90 else ("yellow" if pct >= 60 else "red")
            lines.append(f"{d.isoformat()} | {pct:3d}% | " + color(bar, fg, True))
        return "\n".join(lines)

    def ascii_symptom_trend(self, symptom_name: str) -> str:
        """Average intensity per day over last 7 days, colored."""
        today = date.today()
        lines = [color(f"Symptom trend: {symptom_name} (last 7 days)", "cyan", True)]
        for n in range(7):
            d = today - timedelta(days=n)
            vals = [s.intensity for s in self.symptoms
                    if s.symptom.lower() == symptom_name.lower() and s.date_str == d.isoformat()]
            avg = (sum(vals) / len(vals)) if vals else 0.0
            bar = "#" * int(round(avg))  # 0..5
            fg = "green" if avg <= 2 else ("yellow" if avg <= 3.5 else "red")
            lines.append(f"{d.isoformat()} | {avg:.1f} | " + color(bar, fg, True))
        return "\n".join(lines)

    # ---- Persistence ----
    def to_dict(self) -> Dict:
        return {
            "drugs": [asdict(d) for d in self.drugs],
            "dose_logs": [asdict(l) for l in self.dose_logs],
            "symptoms": [asdict(s) for s in self.symptoms],
        }

    @staticmethod
    def from_dict(d: Dict) -> "MediPal":
        m = MediPal()
        for x in d.get("drugs", []):
            m.drugs.append(Drug(**x))
        for x in d.get("dose_logs", []):
            m.dose_logs.append(DoseLog(**x))
        for x in d.get("symptoms", []):
            m.symptoms.append(SymptomLog(**x))
        return m

# ----------------------------- IO Helpers -----------------------------

def load_medipal() -> MediPal:
    if not os.path.exists(DATA_FILE):
        return MediPal()
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return MediPal.from_dict(json.load(f))
    except Exception:
        return MediPal()

def save_medipal(m: MediPal):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(m.to_dict(), f, ensure_ascii=False, indent=2)

def parse_date(s: str) -> date:
    return datetime.strptime(s, DATE_FMT).date()

def parse_time(s: str) -> time:
    return datetime.strptime(s, TIME_FMT).time()

def input_date(prompt: str) -> date:
    while True:
        s = input(prompt).strip()
        try:
            return parse_date(s)
        except Exception:
            err("Invalid date. Use YYYY-MM-DD.")

def input_time_list(prompt: str) -> List[str]:
    """Accept '08:00, 20:00' -> ['08:00','20:00'] (validated)."""
    while True:
        raw = input(prompt).strip()
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        ok = True
        times = []
        for p in parts:
            try:
                parse_time(p)
                times.append(p)
            except Exception:
                ok = False
                break
        if ok and times:
            return sorted(times)
        warn("Please enter time list like: 08:00, 20:00")

def export_csv(m: MediPal, doses_path="dose_logs.csv", symptoms_path="symptom_logs.csv"):
    with open(doses_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "time", "drug", "status", "note"])
        for l in m.dose_logs:
            w.writerow([l.date_str, l.time_str, l.drug_name, l.status, l.note or ""])
    with open(symptoms_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "symptom", "intensity", "note"])
        for s in m.symptoms:
            w.writerow([s.date_str, s.symptom, s.intensity, s.note or ""])
    ok(f"Exported to {doses_path} and {symptoms_path}")

# ----------------------------- Simple Analysis -----------------------------

def adherence_pct_on(m: MediPal, d: date) -> Optional[float]:
    """Adherence % on a given day (None if no schedule)."""
    sched = m.daily_schedule(d)
    if not sched:
        return None
    hits = sum(1 for (drug, t) in sched if m.get_dose_status(d, t, drug.name) == "TAKEN")
    return hits / len(sched) * 100.0

def symptom_avg_over(m: MediPal, symptom_name: str, days: int) -> float:
    """Average intensity for a symptom over the last N days (including today)."""
    today = date.today()
    vals: List[int] = []
    for n in range(days):
        d = today - timedelta(days=n)
        vals.extend([s.intensity for s in m.symptoms
                     if s.symptom.lower() == symptom_name.lower() and s.date_str == d.isoformat()])
    return round(sum(vals) / len(vals), 2) if vals else 0.0

def symptom_short_trend(m: MediPal, symptom_name: str) -> Tuple[str, float]:
    """Compare last 3 entries vs previous 3 entries: 'up'/'down'/'flat', delta."""
    logs = [s for s in m.symptoms if s.symptom.lower() == symptom_name.lower()]
    logs.sort(key=lambda x: x.date_str)
    if len(logs) < 4:
        return ("flat", 0.0)
    recent = logs[-3:]
    prev = logs[-6:-3]
    if not prev:
        return ("flat", 0.0)
    r_avg = sum(s.intensity for s in recent) / len(recent)
    p_avg = sum(s.intensity for s in prev) / len(prev)
    delta = round(r_avg - p_avg, 2)
    if delta > 0.3:
        return ("up", delta)
    if delta < -0.3:
        return ("down", delta)
    return ("flat", delta)

def analyze_symptom(m: MediPal, symptom_name: str) -> Dict[str, object]:
    """Return simple insights for a symptom."""
    avg7 = symptom_avg_over(m, symptom_name, 7)
    avg14 = symptom_avg_over(m, symptom_name, 14)
    trend, delta = symptom_short_trend(m, symptom_name)

    # Conditional means by adherence across last 14 days
    today = date.today()
    low_days_vals: List[int] = []
    high_days_vals: List[int] = []
    for n in range(14):
        d = today - timedelta(days=n)
        day_vals = [s.intensity for s in m.symptoms
                    if s.symptom.lower() == symptom_name.lower() and s.date_str == d.isoformat()]
        if not day_vals:
            continue
        pct = adherence_pct_on(m, d)
        if pct is None:
            continue
        (low_days_vals if pct < 80 else high_days_vals).extend(day_vals)

    low_avg = round(sum(low_days_vals) / len(low_days_vals), 2) if low_days_vals else None
    high_avg = round(sum(high_days_vals) / len(high_days_vals), 2) if high_days_vals else None

    return {
        "avg7": avg7,
        "avg14": avg14,
        "trend": trend,
        "delta": delta,
        "low_adherence_avg": low_avg,
        "high_adherence_avg": high_avg,
    }

def print_symptom_analysis(m: MediPal, symptom_name: str):
    res = analyze_symptom(m, symptom_name)
    print(color("\n== Symptom analysis ==", "magenta", True))
    print(f"Symptom: {color(symptom_name, 'cyan', True)}")
    print(f"Avg intensity (7d):  {res['avg7']}")
    print(f"Avg intensity (14d): {res['avg14']}")
    trend_txt = {"up": color("worsening ↑", "red", True),
                 "down": color("improving ↓", "green", True),
                 "flat": color("stable →", "yellow", True)}[res["trend"]]
    print(f"Short-term trend (last 3 vs prev 3): {trend_txt} (Δ={res['delta']:+.2f})")
    if res["low_adherence_avg"] is not None and res["high_adherence_avg"] is not None:
        print(f"When adherence <80%:  avg={res['low_adherence_avg']}")
        print(f"When adherence ≥80%:  avg={res['high_adherence_avg']}")
        if res["low_adherence_avg"] > res["high_adherence_avg"]:
            warn("Hint: symptoms are higher on low-adherence days. Try improving dose adherence.")
    else:
        warn("Hint: need more data to compare symptom vs adherence (last 14 days).")

# ----------------------------- CLI Flows -----------------------------

def ensure_sample(m: MediPal):
    if m.drugs:
        return
    m.add_drug(Drug(
        name="Amoxicillin",
        dosage="500mg",
        times=["08:00", "20:00"],
        start_date=(date.today() - timedelta(days=1)).isoformat(),
        end_date=(date.today() + timedelta(days=5)).isoformat(),
        notes="After meal"
    ))
    m.add_drug(Drug(
        name="Vitamin D",
        dosage="1000 IU",
        times=["09:00"],
        start_date=(date.today() - timedelta(days=10)).isoformat(),
        notes="Morning"
    ))
    # Optional demo symptoms
    today = date.today()
    m.symptoms.extend([
        SymptomLog((today - timedelta(days=3)).isoformat(), "headache", 2, None),
        SymptomLog((today - timedelta(days=2)).isoformat(), "headache", 3, None),
        SymptomLog((today - timedelta(days=1)).isoformat(), "headache", 4, None),
    ])
    save_medipal(m)

def menu_list_drugs(m: MediPal):
    drugs = m.list_drugs()
    if not drugs:
        print(color("(No drugs)", "gray"))
        return
    print(color("\n# Drugs", "cyan", True))
    print("Idx | Name | Dosage | Times | Start -> End | Notes")
    print("-" * 72)
    for i, d in enumerate(drugs):
        end = d.end_date or "open-ended"
        print(f"{i:>3} | {d.name} | {d.dosage} | {', '.join(d.times)} | {d.start_date} -> {end} | {d.notes or ''}")

def menu_add_drug(m: MediPal):
    print(color("\n== Add Drug ==", "magenta", True))
    name = input("Name: ").strip()
    dosage = input("Dosage (e.g., 500mg): ").strip()
    times = input_time_list("Times (comma-separated HH:MM): ")
    sd = input_date("Start date (YYYY-MM-DD): ").isoformat()
    ed_in = input("End date (YYYY-MM-DD, Enter for none): ").strip()
    ed = None
    if ed_in:
        try:
            ed = parse_date(ed_in).isoformat()
        except Exception:
            warn("Invalid end date; set to none.")
            ed = None
    notes = input("Notes (optional): ").strip() or None
    m.add_drug(Drug(name, dosage, times, sd, ed, notes))
    save_medipal(m)
    ok("Added.")

def menu_delete_drug(m: MediPal):
    # Build a sorted view (display index -> original index)
    pairs = sorted(list(enumerate(m.drugs)), key=lambda p: p[1].name.lower())
    if not pairs:
        print(color("(No drugs)", "gray"))
        return

    print(color("\n# Drugs", "cyan", True))
    print("Idx | Name | Dosage | Times | Start -> End | Notes")
    print("-" * 72)
    for disp_idx, (orig_idx, d) in enumerate(pairs):
        end = d.end_date or "open-ended"
        print(f"{disp_idx:>3} | {d.name} | {d.dosage} | {', '.join(d.times)} | {d.start_date} -> {end} | {d.notes or ''}")

    try:
        disp = int(input("Idx to delete: ").strip())
    except Exception:
        err("Invalid index.")
        return
    if not (0 <= disp < len(pairs)):
        err("Invalid index.")
        return

    orig_idx = pairs[disp][0]
    d = m.remove_drug(orig_idx)
    if d:
        save_medipal(m)
        ok(f"Deleted {d.name}")

def menu_schedule(m: MediPal):
    d = input_date("Which date (YYYY-MM-DD, default today)? ") if input("Custom date? (y/N): ").strip().lower()=="y" else date.today()
    sched = m.daily_schedule(d)
    if not sched:
        print(color("(No scheduled doses)", "gray"))
        return
    print(color(f"\n# Schedule for {d.isoformat()}", "cyan", True))
    print("Idx | Time | Drug (dosage) | Status")
    print("-" * 54)
    for i, (drug, t) in enumerate(sched):
        st = m.get_dose_status(d, t, drug.name) or "-"
        if st == "TAKEN":
            st_col = color("TAKEN", "green", True)
        elif st == "MISSED":
            st_col = color("MISSED", "red", True)
        else:
            st_col = color("-", "gray")
        print(f"{i:>3} | {t.strftime(TIME_FMT)} | {drug.name} ({drug.dosage}) | {st_col}")

    cmd = input("\nMark one? (e.g., '2 TAKEN' or '3 MISSED', Enter to skip): ").strip()
    if not cmd:
        return
    try:
        idx_s, status = cmd.split()
        idx = int(idx_s)
        status = status.upper()
        drug, t = sched[idx]
        m.mark_dose(d, t, drug.name, status)
        save_medipal(m)
        ok("Recorded.")
    except Exception:
        err("Invalid input.")

def menu_add_symptom(m: MediPal):
    print(color("\n== Add Symptom ==", "magenta", True))
    ds = input_date("Date (YYYY-MM-DD): ").isoformat()
    name = input("Symptom name: ").strip()
    try:
        intensity = int(input("Intensity (1-5): ").strip())
    except Exception:
        err("Must be an integer 1-5.")
        return
    note = input("Note (optional): ").strip() or None
    try:
        m.add_symptom(SymptomLog(ds, name, intensity, note))
        save_medipal(m)
        ok("Logged.")
        # Instant analysis
        print_symptom_analysis(m, name)
        print(m.ascii_symptom_trend(name))
    except ValueError as e:
        err(f"Error: {e}")

def menu_stats(m: MediPal):
    print(color("\n== Weekly Adherence ==", "magenta", True))
    taken, expected, pct = m.adherence_last_7_days()
    print(f"Taken {taken} / Expected {expected} = {color(str(pct)+'%', 'cyan', True)}")
    print(m.ascii_weekly_adherence())

    ask = input("\nShow a symptom trend & analysis? (name or Enter to skip): ").strip()
    if ask:
        print_symptom_analysis(m, ask)
        print(m.ascii_symptom_trend(ask))

def main_menu():
    m = load_medipal()
    ensure_sample(m)
    while True:
        print(color("\n====== MediPal ======", "blue", True))
        print("1. List drugs")
        print("2. Add drug")
        print("3. Delete drug")
        print("4. Show schedule & mark dose")
        print("5. Log a symptom (with instant analysis)")
        print("6. Weekly stats & symptom insights")
        print("7. Export CSV logs")
        print("8. Exit")
        cmd = input("Choose: ").strip()

        if cmd == "1":
            menu_list_drugs(m)
        elif cmd == "2":
            menu_add_drug(m)
        elif cmd == "3":
            menu_delete_drug(m)
        elif cmd == "4":
            menu_schedule(m)
        elif cmd == "5":
            menu_add_symptom(m)
        elif cmd == "6":
            menu_stats(m)
        elif cmd == "7":
            export_csv(m)
        elif cmd == "8":
            print(color("Stay well! 💊", "green", True))
            break
        else:
            err("Invalid choice.")

if __name__ == "__main__":
    main_menu()

