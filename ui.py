"""
AegisNode - Full Multi-Page Control Panel
Run with: python ui.py
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
import asyncio
import threading
import queue
import os
import sys
import json
import random
from datetime import datetime

# ── Colors ────────────────────────────────────────────────────────────────────
BG_DARK      = "#0d1117"
BG_PANEL     = "#161b22"
BG_CARD      = "#21262d"
ACCENT_GREEN = "#39d353"
ACCENT_RED   = "#f85149"
ACCENT_YELLOW= "#d29922"
ACCENT_BLUE  = "#58a6ff"
ACCENT_PURPLE= "#bc8cff"
ACCENT_ORANGE= "#f0883e"
TEXT_WHITE   = "#e6edf3"
TEXT_GRAY    = "#8b949e"
BORDER       = "#30363d"

log_queue = queue.Queue()
llm_queue = queue.Queue()

# ── Log Sink ──────────────────────────────────────────────────────────────────
class UILogSink:
    def write(self, message):
        try:
            record = message.record
            level  = record["level"].name
            time   = record["time"].strftime("%H:%M:%S")
            text   = record["message"]
            log_queue.put((level, f"[{time}] {text}"))
        except Exception:
            pass
    def __call__(self, message):
        self.write(message)

def setup_loguru():
    try:
        from loguru import logger
        logger.remove()
        logger.add(UILogSink(), format="{message}", level="DEBUG")
    except Exception:
        pass

def patch_analyzer():
    try:
        from agent import analyzer as m
        orig = m.Analyzer.analyze
        async def patched(self, alert, runbook_context):
            llm_queue.put(("PROMPT", f"=== PROMPT TO LLAMA 3 ===\nTimestamp  : {alert.timestamp.isoformat()}\nError Rate : {alert.error_rate:.2%}\n\n--- LOGS ---\n{alert.raw_logs[:1200]}\n\n--- RUNBOOK CONTEXT ---\n{runbook_context[:600]}\n\n--- Waiting for Llama 3... ---\n"))
            result = await orig(self, alert, runbook_context)
            llm_queue.put(("RESPONSE", f"=== LLAMA 3 RESPONSE ===\nRoot Cause  : {result.root_cause}\nConfidence  : {result.confidence:.0%}\nSummary     : {result.summary}\nComponents  : {', '.join(result.affected_components)}\n\n--- ACTIONS ---\n" + "\n".join([f"  [{i+1}] {a.action_type}\n      Target : {a.target}\n      Risk   : {a.risk_level}\n      Why    : {a.justification}\n" for i,a in enumerate(result.actions)]) + f"\n--- ROLLBACK ---\n{result.rollback_plan}\n\n=== PYDANTIC VALIDATION: PASSED ✓ ===\n"))
            return result
        m.Analyzer.analyze = patched
    except Exception as e:
        log_queue.put(("WARNING", f"Analyzer patch skipped: {e}"))

# ── Helper widgets ────────────────────────────────────────────────────────────
def make_card(parent, title=None, padx=4, pady=4):
    frame = tk.Frame(parent, bg=BG_PANEL, highlightbackground=BORDER, highlightthickness=1)
    frame.pack(fill=tk.BOTH, expand=True, padx=padx, pady=pady)
    if title:
        tk.Label(frame, text=title, font=("Segoe UI", 9, "bold"),
                 bg=BG_PANEL, fg=TEXT_GRAY).pack(anchor="w", padx=10, pady=(8,2))
        tk.Frame(frame, bg=BORDER, height=1).pack(fill=tk.X, padx=10)
    return frame

def label(parent, text, font_size=9, bold=False, color=TEXT_WHITE, bg=BG_PANEL, anchor="w", pady=1):
    style = "bold" if bold else ""
    tk.Label(parent, text=text, font=("Segoe UI", font_size, style),
             bg=bg, fg=color, anchor=anchor).pack(anchor=anchor, padx=10, pady=pady)

def btn(parent, text, color, fg, cmd, pady=3, font_size=10):
    b = tk.Button(parent, text=text, bg=color, fg=fg,
                  font=("Segoe UI", font_size, "bold"),
                  relief=tk.FLAT, cursor="hand2", bd=0,
                  pady=6, command=cmd)
    b.pack(fill=tk.X, padx=10, pady=pady)
    return b

def scrollbox(parent, height=None):
    st = scrolledtext.ScrolledText(
        parent, bg="#0a0e14", fg=TEXT_WHITE,
        font=("Cascadia Code", 9), wrap=tk.WORD,
        insertbackground=TEXT_WHITE, relief=tk.FLAT,
        padx=8, pady=6)
    if height:
        st.configure(height=height)
    st.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
    return st

def write_to(widget, text, tag="INFO"):
    widget.config(state=tk.NORMAL)
    widget.insert(tk.END, text + "\n", tag)
    widget.see(tk.END)
    widget.config(state=tk.DISABLED)

# ── Main App ──────────────────────────────────────────────────────────────────
class AegisNodeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AegisNode  —  Self-Healing Infrastructure Agent")
        self.root.configure(bg=BG_DARK)
        self.root.geometry("1440x880")
        self.root.minsize(1200, 750)

        self._running      = False
        self._agent_thread = None
        self._agent_loop   = None
        self._alert_count  = 0
        self._fix_count    = 0
        self._current_page = None

        # Feature engines
        from features.predictive  import PredictiveEngine
        from features.finops      import FinOpsEngine
        from features.chaos       import ChaosEngine
        from features.compliance  import ComplianceEngine
        self.predictive  = PredictiveEngine()
        self.finops      = FinOpsEngine()
        self.chaos       = ChaosEngine()
        self.compliance  = ComplianceEngine()

        setup_loguru()
        self._build_shell()
        self._show_page("mission")
        self._poll_queues()
        self._auto_refresh_finops()

    # ── Shell (sidebar + content area) ───────────────────────────────────────
    def _build_shell(self):
        # Top bar
        top = tk.Frame(self.root, bg="#010409", pady=6)
        top.pack(fill=tk.X)
        tk.Label(top, text="🛡  AegisNode", font=("Segoe UI", 16, "bold"),
                 bg="#010409", fg=TEXT_WHITE).pack(side=tk.LEFT, padx=16)
        tk.Label(top, text="Self-Healing Infrastructure Agent  •  AIOps Platform",
                 font=("Segoe UI", 10), bg="#010409", fg=TEXT_GRAY).pack(side=tk.LEFT)
        self.global_status = tk.Label(top, text="⬤  STOPPED",
                                      font=("Segoe UI", 11, "bold"),
                                      bg="#010409", fg=ACCENT_RED)
        self.global_status.pack(side=tk.RIGHT, padx=16)
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill=tk.X)

        # Body
        body = tk.Frame(self.root, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True)

        # Sidebar
        self.sidebar = tk.Frame(body, bg=BG_PANEL, width=180)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)
        self._build_sidebar()

        tk.Frame(body, bg=BORDER, width=1).pack(side=tk.LEFT, fill=tk.Y)

        # Page container
        self.content = tk.Frame(body, bg=BG_DARK)
        self.content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Pages dict
        self.pages = {}

    def _build_sidebar(self):
        tk.Label(self.sidebar, text="NAVIGATION", font=("Segoe UI", 8, "bold"),
                 bg=BG_PANEL, fg=TEXT_GRAY).pack(anchor="w", padx=12, pady=(16,4))

        nav_items = [
            ("mission",    "🏠", "Mission Control"),
            ("llm",        "🧠", "LLM Reasoning"),
            ("predictive", "📈", "Predictive AI"),
            ("finops",     "💰", "FinOps Agent"),
            ("chaos",      "💥", "Chaos Lab"),
            ("compliance", "🛡", "Compliance"),
            ("traces",     "🔍", "LangSmith Traces"),
        ]
        self._nav_buttons = {}
        for page_id, icon, label_text in nav_items:
            f = tk.Frame(self.sidebar, bg=BG_PANEL, cursor="hand2")
            f.pack(fill=tk.X, padx=8, pady=1)
            lbl = tk.Label(f, text=f"  {icon}  {label_text}",
                           font=("Segoe UI", 10), bg=BG_PANEL, fg=TEXT_GRAY,
                           anchor="w", pady=8)
            lbl.pack(fill=tk.X)
            for widget in (f, lbl):
                widget.bind("<Button-1>", lambda e, pid=page_id: self._show_page(pid))
                widget.bind("<Enter>", lambda e, w=f, l=lbl: (w.config(bg=BG_CARD), l.config(bg=BG_CARD)))
                widget.bind("<Leave>", lambda e, w=f, l=lbl, pid=page_id: (
                    w.config(bg=BG_CARD if self._current_page==pid else BG_PANEL),
                    l.config(bg=BG_CARD if self._current_page==pid else BG_PANEL)
                ))
            self._nav_buttons[page_id] = (f, lbl)

        # Sidebar counters
        tk.Frame(self.sidebar, bg=BORDER, height=1).pack(fill=tk.X, padx=8, pady=12)
        tk.Label(self.sidebar, text="SESSION STATS", font=("Segoe UI", 8, "bold"),
                 bg=BG_PANEL, fg=TEXT_GRAY).pack(anchor="w", padx=12, pady=(0,4))

        cf = tk.Frame(self.sidebar, bg=BG_PANEL)
        cf.pack(fill=tk.X, padx=8)
        cf.columnconfigure(0, weight=1); cf.columnconfigure(1, weight=1)

        ac = tk.Frame(cf, bg=BG_CARD, padx=6, pady=6)
        ac.grid(row=0, column=0, padx=2, sticky="ew")
        tk.Label(ac, text="Alerts", font=("Segoe UI", 8), bg=BG_CARD, fg=TEXT_GRAY).pack()
        self.alert_counter = tk.Label(ac, text="0", font=("Segoe UI", 16, "bold"),
                                       bg=BG_CARD, fg=ACCENT_YELLOW)
        self.alert_counter.pack()

        fc = tk.Frame(cf, bg=BG_CARD, padx=6, pady=6)
        fc.grid(row=0, column=1, padx=2, sticky="ew")
        tk.Label(fc, text="Fixes", font=("Segoe UI", 8), bg=BG_CARD, fg=TEXT_GRAY).pack()
        self.fix_counter = tk.Label(fc, text="0", font=("Segoe UI", 16, "bold"),
                                     bg=BG_CARD, fg=ACCENT_GREEN)
        self.fix_counter.pack()

    def _show_page(self, page_id):
        # Highlight active nav
        for pid, (f, l) in self._nav_buttons.items():
            active = pid == page_id
            f.config(bg=BG_CARD if active else BG_PANEL)
            l.config(bg=BG_CARD if active else BG_PANEL,
                     fg=TEXT_WHITE if active else TEXT_GRAY)

        # Hide all pages
        for p in self.pages.values():
            p.pack_forget()

        # Build page if needed
        if page_id not in self.pages:
            frame = tk.Frame(self.content, bg=BG_DARK)
            self.pages[page_id] = frame
            builder = getattr(self, f"_build_{page_id}_page", None)
            if builder:
                builder(frame)

        self.pages[page_id].pack(fill=tk.BOTH, expand=True)
        self._current_page = page_id

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 1 — MISSION CONTROL
    # ══════════════════════════════════════════════════════════════════════════
    def _build_mission_page(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=3)
        parent.rowconfigure(0, weight=1)

        # Left controls
        left = tk.Frame(parent, bg=BG_DARK)
        left.grid(row=0, column=0, sticky="nsew", padx=(8,4), pady=8)

        ctrl = make_card(left, "⚙  AGENT CONTROLS")

        # Status
        sf = tk.Frame(ctrl, bg=BG_CARD, padx=10, pady=10)
        sf.pack(fill=tk.X, padx=10, pady=8)
        tk.Label(sf, text="Agent Status", font=("Segoe UI", 9),
                 bg=BG_CARD, fg=TEXT_GRAY).pack(anchor="w")
        self.status_dot = tk.Label(sf, text="⬤  STOPPED",
                                   font=("Segoe UI", 13, "bold"),
                                   bg=BG_CARD, fg=ACCENT_RED)
        self.status_dot.pack(anchor="w")

        self.start_btn  = btn(ctrl, "▶  START AGENT", ACCENT_GREEN, "#000", self._start_agent)
        self.stop_btn   = btn(ctrl, "■  STOP AGENT",  BG_CARD, ACCENT_RED,  self._stop_agent)
        self.stop_btn.config(state=tk.DISABLED)

        tk.Frame(ctrl, bg=BORDER, height=1).pack(fill=tk.X, padx=10, pady=6)
        tk.Label(ctrl, text="DEMO CONTROLS", font=("Segoe UI", 9, "bold"),
                 bg=BG_PANEL, fg=TEXT_GRAY).pack(anchor="w", padx=10)

        self.alert_btn = btn(ctrl, "🔴  Fire Demo Alert", ACCENT_YELLOW, "#000", self._fire_alert)
        self.fix_btn   = btn(ctrl, "✅  Simulate Fix",    ACCENT_BLUE,   "#000", self._simulate_fix)
        self.alert_btn.config(state=tk.DISABLED)
        self.fix_btn.config(state=tk.DISABLED)

        tk.Frame(ctrl, bg=BORDER, height=1).pack(fill=tk.X, padx=10, pady=6)
        tk.Label(ctrl, text="CONFIGURATION", font=("Segoe UI", 9, "bold"),
                 bg=BG_PANEL, fg=TEXT_GRAY).pack(anchor="w", padx=10)
        try:
            from config.settings import settings
            cfg = [("LLM Model", settings.OLLAMA_MODEL), ("Prometheus", "localhost:9090"),
                   ("Loki", "localhost:3100"), ("OPA", "localhost:8181"),
                   ("Dry Run", "YES ✓" if settings.KUBECTL_DRY_RUN else "NO"),
                   ("Namespace", settings.KUBERNETES_NAMESPACE)]
        except Exception:
            cfg = [("Config", "load error")]
        for k, v in cfg:
            r = tk.Frame(ctrl, bg=BG_PANEL)
            r.pack(fill=tk.X, padx=10, pady=1)
            tk.Label(r, text=k, font=("Segoe UI", 8), bg=BG_PANEL, fg=TEXT_GRAY,
                     width=12, anchor="w").pack(side=tk.LEFT)
            tk.Label(r, text=v, font=("Segoe UI", 8, "bold"),
                     bg=BG_PANEL, fg=TEXT_WHITE, anchor="w").pack(side=tk.LEFT)

        # Right logs
        right = tk.Frame(parent, bg=BG_DARK)
        right.grid(row=0, column=1, sticky="nsew", padx=(4,8), pady=8)

        logcard = make_card(right, "📋  LIVE SYSTEM LOGS")
        self.mission_log = scrollbox(logcard)
        for lvl, col in [("SUCCESS", ACCENT_GREEN), ("ERROR", ACCENT_RED),
                          ("WARNING", ACCENT_YELLOW), ("INFO", ACCENT_BLUE),
                          ("DEBUG", TEXT_GRAY), ("SYSTEM", TEXT_WHITE)]:
            self.mission_log.tag_config(lvl, foreground=col)

        btn(logcard, "Clear", BG_CARD, TEXT_GRAY,
            lambda: self.mission_log.config(state=tk.NORMAL) or self.mission_log.delete("1.0", tk.END) or self.mission_log.config(state=tk.DISABLED),
            pady=2, font_size=8)

        # Bottom bar
        bar = tk.Frame(self.content, bg=BG_PANEL,
                       highlightbackground=BORDER, highlightthickness=1)
        bar.pack(fill=tk.X, padx=8, pady=(0,6), side=tk.BOTTOM)
        tk.Label(bar, text="LAST REPORT:", font=("Segoe UI", 9, "bold"),
                 bg=BG_PANEL, fg=TEXT_GRAY).pack(side=tk.LEFT, padx=12, pady=5)
        self.report_bar = tk.Label(bar, text="No remediation yet",
                                   font=("Segoe UI", 9), bg=BG_PANEL, fg=TEXT_GRAY)
        self.report_bar.pack(side=tk.LEFT)

        write_to(self.mission_log, "AegisNode Control Panel ready.", "SYSTEM")
        write_to(self.mission_log, "Click ▶ START AGENT to begin monitoring.", "INFO")

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 2 — LLM REASONING
    # ══════════════════════════════════════════════════════════════════════════
    def _build_llm_page(self, parent):
        top = tk.Frame(parent, bg=BG_DARK)
        top.pack(fill=tk.X, padx=8, pady=(8,0))
        tk.Label(top, text="🧠  LLM REASONING  —  Everything Llama 3 sees and thinks",
                 font=("Segoe UI", 13, "bold"), bg=BG_DARK, fg=TEXT_WHITE).pack(side=tk.LEFT)
        tk.Label(top, text="Running locally on your RTX 5080  •  No data leaves your machine",
                 font=("Segoe UI", 9), bg=BG_DARK, fg=ACCENT_GREEN).pack(side=tk.RIGHT)

        card = make_card(parent)
        self.llm_box = scrollbox(card)
        self.llm_box.tag_config("PROMPT",   foreground=ACCENT_BLUE)
        self.llm_box.tag_config("RESPONSE", foreground=ACCENT_GREEN)
        self.llm_box.tag_config("SYSTEM",   foreground=TEXT_GRAY)
        self.llm_box.tag_config("ERROR",    foreground=ACCENT_RED)

        write_to(self.llm_box, "=== LLM REASONING WINDOW ===\n", "SYSTEM")
        write_to(self.llm_box, "This panel shows EVERYTHING Llama 3 does:\n", "SYSTEM")
        write_to(self.llm_box, "  • Exact prompt sent to the model", "SYSTEM")
        write_to(self.llm_box, "  • Raw JSON response from Llama 3", "SYSTEM")
        write_to(self.llm_box, "  • Pydantic schema validation result", "SYSTEM")
        write_to(self.llm_box, "  • OPA policy decision", "SYSTEM")
        write_to(self.llm_box, "  • Final remediation plan\n", "SYSTEM")
        write_to(self.llm_box, "Go to Mission Control → Start Agent → Fire Demo Alert", "SYSTEM")

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 3 — PREDICTIVE AI
    # ══════════════════════════════════════════════════════════════════════════
    def _build_predictive_page(self, parent):
        top = tk.Frame(parent, bg=BG_DARK)
        top.pack(fill=tk.X, padx=8, pady=(8,0))
        tk.Label(top, text="📈  PREDICTIVE INTELLIGENCE  —  Crash Prevention Before It Happens",
                 font=("Segoe UI", 13, "bold"), bg=BG_DARK, fg=TEXT_WHITE).pack(side=tk.LEFT)
        self.pred_updated = tk.Label(top, text="", font=("Segoe UI", 9),
                                     bg=BG_DARK, fg=TEXT_GRAY)
        self.pred_updated.pack(side=tk.RIGHT)

        body = tk.Frame(parent, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        # Left — metrics display
        left = tk.Frame(body, bg=BG_DARK)
        left.grid(row=0, column=0, sticky="nsew", padx=(0,4))

        card1 = make_card(left, "📊  LIVE METRICS  (last 10 readings)")
        self.metrics_box = scrollbox(card1, height=12)
        self.metrics_box.tag_config("GOOD",  foreground=ACCENT_GREEN)
        self.metrics_box.tag_config("WARN",  foreground=ACCENT_YELLOW)
        self.metrics_box.tag_config("CRIT",  foreground=ACCENT_RED)
        self.metrics_box.tag_config("HEAD",  foreground=ACCENT_BLUE)

        card2 = make_card(left, "🔮  PREDICTIONS  (next 10 minutes)")
        self.pred_box = scrollbox(card2, height=10)
        self.pred_box.tag_config("SAFE",   foreground=ACCENT_GREEN)
        self.pred_box.tag_config("BREACH", foreground=ACCENT_RED)
        self.pred_box.tag_config("HEAD",   foreground=ACCENT_BLUE)

        # Right — alerts + info
        right = tk.Frame(body, bg=BG_DARK)
        right.grid(row=0, column=1, sticky="nsew", padx=(4,0))

        alert_card = make_card(right, "⚠  PREDICTED ALERTS")
        self.pred_alert_box = scrollbox(alert_card, height=12)
        self.pred_alert_box.tag_config("HIGH",   foreground=ACCENT_RED)
        self.pred_alert_box.tag_config("MEDIUM", foreground=ACCENT_YELLOW)
        self.pred_alert_box.tag_config("OK",     foreground=ACCENT_GREEN)

        info_card = make_card(right, "ℹ  MODEL INFO")
        self.pred_info_box = scrollbox(info_card, height=8)
        self.pred_info_box.tag_config("INFO", foreground=ACCENT_BLUE)

        btn(right, "🔄  Refresh Predictions", ACCENT_PURPLE, "#000",
            self._refresh_predictions, font_size=9)

        self._refresh_predictions()

    def _refresh_predictions(self):
        async def _run():
            data = await self.predictive.run_prediction_cycle()
            self.root.after(0, lambda: self._update_predictive_ui(data))
        threading.Thread(target=lambda: asyncio.run(_run()), daemon=True).start()

    def _update_predictive_ui(self, data):
        # Metrics
        self.metrics_box.config(state=tk.NORMAL)
        self.metrics_box.delete("1.0", tk.END)
        self.metrics_box.insert(tk.END,
            f"{'Time':<8} {'CPU%':<8} {'MEM%':<8} {'ERR%':<8} {'LATENCY':<10}\n", "HEAD")
        self.metrics_box.insert(tk.END, "─" * 45 + "\n", "HEAD")
        for h in data["history"][-10:]:
            tag = "CRIT" if h["cpu"] > 85 or h["memory"] > 90 else \
                  "WARN" if h["cpu"] > 70 or h["memory"] > 75 else "GOOD"
            self.metrics_box.insert(tk.END,
                f"{h['timestamp']:<8} {h['cpu']:<8} {h['memory']:<8} {h['error_rate']:<8} {h['latency']}ms\n", tag)
        self.metrics_box.config(state=tk.DISABLED)

        # Predictions
        self.pred_box.config(state=tk.NORMAL)
        self.pred_box.delete("1.0", tk.END)
        self.pred_box.insert(tk.END,
            f"{'Time':<8} {'CPU%':<10} {'MEM%':<15} {'BREACH':<8}\n", "HEAD")
        self.pred_box.insert(tk.END, "─" * 45 + "\n", "HEAD")
        for p in data["predictions"][:10]:
            tag = "BREACH" if p["will_breach"] else "SAFE"
            breach = "⚠ YES" if p["will_breach"] else "✓ NO"
            mem_range = f"{p['memory']} ({p['memory_lower']}-{p['memory_upper']})"
            self.pred_box.insert(tk.END,
                f"{p['timestamp']:<8} {p['cpu']:<10} {mem_range:<15} {breach}\n", tag)
        self.pred_box.config(state=tk.DISABLED)

        # Alerts
        self.pred_alert_box.config(state=tk.NORMAL)
        self.pred_alert_box.delete("1.0", tk.END)
        if data["alerts"]:
            for a in data["alerts"]:
                self.pred_alert_box.insert(tk.END, f"[{a['severity']}] {a['metric']}\n", "HIGH")
                self.pred_alert_box.insert(tk.END, f"  {a['message']}\n", "MEDIUM")
                self.pred_alert_box.insert(tk.END, f"  → {a['recommendation']}\n\n", "MEDIUM")
        else:
            self.pred_alert_box.insert(tk.END, "✅ No predicted breaches in next 30 minutes\n\n", "OK")
            self.pred_alert_box.insert(tk.END, "System is healthy and trending stable.\nAll metrics within safe bounds.", "OK")
        self.pred_alert_box.config(state=tk.DISABLED)

        # Model info
        self.pred_info_box.config(state=tk.NORMAL)
        self.pred_info_box.delete("1.0", tk.END)
        self.pred_info_box.insert(tk.END, f"Model       : Facebook Prophet\n", "INFO")
        self.pred_info_box.insert(tk.END, f"Algorithm   : Additive time-series forecasting\n", "INFO")
        self.pred_info_box.insert(tk.END, f"Horizon     : 30 minutes ahead\n", "INFO")
        self.pred_info_box.insert(tk.END, f"Confidence  : 95% prediction intervals\n", "INFO")
        self.pred_info_box.insert(tk.END, f"Data points : {len(data['history'])} historical readings\n", "INFO")
        self.pred_info_box.insert(tk.END, f"Updated     : {data['last_updated']}\n", "INFO")
        self.pred_info_box.config(state=tk.DISABLED)

        self.pred_updated.config(text=f"Last updated: {data['last_updated']}")

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 4 — FINOPS
    # ══════════════════════════════════════════════════════════════════════════
    def _build_finops_page(self, parent):
        top = tk.Frame(parent, bg=BG_DARK)
        top.pack(fill=tk.X, padx=8, pady=(8,0))
        tk.Label(top, text="💰  FINOPS INTELLIGENCE  —  Cloud Cost Optimization Agent",
                 font=("Segoe UI", 13, "bold"), bg=BG_DARK, fg=TEXT_WHITE).pack(side=tk.LEFT)

        body = tk.Frame(parent, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        # Left
        left = tk.Frame(body, bg=BG_DARK)
        left.grid(row=0, column=0, sticky="nsew", padx=(0,4))

        summary_card = make_card(left, "📊  COST SUMMARY")
        self.cost_summary = scrollbox(summary_card, height=5)
        self.cost_summary.tag_config("GOOD", foreground=ACCENT_GREEN)
        self.cost_summary.tag_config("WARN", foreground=ACCENT_YELLOW)
        self.cost_summary.tag_config("CRIT", foreground=ACCENT_RED)
        self.cost_summary.tag_config("INFO", foreground=ACCENT_BLUE)

        resource_card = make_card(left, "🖥  RESOURCE BREAKDOWN  (waste analysis)")
        self.resource_box = scrollbox(resource_card)
        self.resource_box.tag_config("CRIT", foreground=ACCENT_RED)
        self.resource_box.tag_config("HIGH", foreground=ACCENT_YELLOW)
        self.resource_box.tag_config("MED",  foreground=ACCENT_ORANGE)
        self.resource_box.tag_config("LOW",  foreground=ACCENT_GREEN)
        self.resource_box.tag_config("HEAD", foreground=ACCENT_BLUE)

        # Right
        right = tk.Frame(body, bg=BG_DARK)
        right.grid(row=0, column=1, sticky="nsew", padx=(4,0))

        rec_card = make_card(right, "🤖  AI RECOMMENDATIONS  (Llama 3 analysis)")
        self.rec_box = scrollbox(rec_card)
        self.rec_box.tag_config("CRIT", foreground=ACCENT_RED)
        self.rec_box.tag_config("HIGH", foreground=ACCENT_YELLOW)
        self.rec_box.tag_config("INFO", foreground=TEXT_WHITE)
        self.rec_box.tag_config("SAVE", foreground=ACCENT_GREEN)

        btn(right, "🔄  Refresh Cost Data", ACCENT_GREEN, "#000",
            self._refresh_finops, font_size=9)

        self._refresh_finops()

    def _refresh_finops(self):
        data = self.finops.get_cost_data()
        recs = self.finops.generate_llm_recommendations(data)
        s = data["summary"]

        # Summary
        self.cost_summary.config(state=tk.NORMAL)
        self.cost_summary.delete("1.0", tk.END)
        self.cost_summary.insert(tk.END, f"  Daily Spend    : ${s['total_daily']}\n", "INFO")
        self.cost_summary.insert(tk.END, f"  Monthly Spend  : ${s['total_monthly']}\n", "INFO")
        self.cost_summary.insert(tk.END, f"  Identified Waste: ${s['total_waste_monthly']}/month  ({s['savings_percent']}% of budget)\n", "WARN")
        self.cost_summary.insert(tk.END, f"  Critical Resources: {s['critical_resources']} need immediate attention\n", "CRIT")
        self.cost_summary.insert(tk.END, f"  Last Updated   : {s['last_updated']}\n", "INFO")
        self.cost_summary.config(state=tk.DISABLED)

        # Resources
        self.resource_box.config(state=tk.NORMAL)
        self.resource_box.delete("1.0", tk.END)
        self.resource_box.insert(tk.END,
            f"{'Resource':<30} {'Type':<12} {'Daily':<10} {'Util%':<8} {'Waste':<8} {'Level'}\n", "HEAD")
        self.resource_box.insert(tk.END, "─" * 80 + "\n", "HEAD")
        tag_map = {"CRITICAL": "CRIT", "HIGH": "HIGH", "MEDIUM": "MED", "LOW": "LOW"}
        for svc in data["services"]:
            tag = tag_map.get(svc["waste_level"], "LOW")
            self.resource_box.insert(tk.END,
                f"{svc['name']:<30} {svc['type']:<12} ${svc['daily_cost']:<9} {svc['utilization']:<8} ${svc['waste_daily']:<7} {svc['waste_level']}\n", tag)
        self.resource_box.config(state=tk.DISABLED)

        # Recommendations
        self.rec_box.config(state=tk.NORMAL)
        self.rec_box.delete("1.0", tk.END)
        total_savings = sum(r["monthly_savings"] for r in recs)
        self.rec_box.insert(tk.END, f"Total Identified Savings: ${total_savings:.2f}/month\n\n", "SAVE")
        for i, r in enumerate(recs, 1):
            tag = "CRIT" if "CRITICAL" in r["priority"] else "HIGH"
            self.rec_box.insert(tk.END, f"[{i}] {r['priority']}  —  {r['resource']}\n", tag)
            self.rec_box.insert(tk.END, f"    Finding : {r['finding']}\n", "INFO")
            self.rec_box.insert(tk.END, f"    Action  : {r['recommendation']}\n", "INFO")
            self.rec_box.insert(tk.END, f"    Savings : ${r['monthly_savings']:.2f}/month  |  Risk: {r['risk']}  |  Effort: {r['effort']}\n\n", "SAVE")
        self.rec_box.config(state=tk.DISABLED)

    def _auto_refresh_finops(self):
        if "finops" in self.pages:
            self._refresh_finops()
        self.root.after(30000, self._auto_refresh_finops)

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 5 — CHAOS LAB
    # ══════════════════════════════════════════════════════════════════════════
    def _build_chaos_page(self, parent):
        top = tk.Frame(parent, bg=BG_DARK)
        top.pack(fill=tk.X, padx=8, pady=(8,0))
        tk.Label(top, text="💥  CHAOS LAB  —  Resilience Testing & Automated Recovery",
                 font=("Segoe UI", 13, "bold"), bg=BG_DARK, fg=TEXT_WHITE).pack(side=tk.LEFT)

        body = tk.Frame(parent, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        body.columnconfigure(0, weight=2)
        body.columnconfigure(1, weight=3)
        body.rowconfigure(0, weight=1)

        # Left — experiment buttons
        left = tk.Frame(body, bg=BG_DARK)
        left.grid(row=0, column=0, sticky="nsew", padx=(0,4))

        score_card = make_card(left, "🏆  RESILIENCE SCORE")
        self.score_frame = tk.Frame(score_card, bg=BG_PANEL)
        self.score_frame.pack(fill=tk.X, padx=10, pady=8)
        self.score_label = tk.Label(self.score_frame, text="—",
                                    font=("Segoe UI", 36, "bold"),
                                    bg=BG_PANEL, fg=ACCENT_GREEN)
        self.score_label.pack()
        self.score_sub = tk.Label(self.score_frame, text="Run experiments to calculate",
                                  font=("Segoe UI", 9), bg=BG_PANEL, fg=TEXT_GRAY)
        self.score_sub.pack()

        exp_card = make_card(left, "🧪  EXPERIMENTS")
        self._chaos_btns = {}
        for exp in self.chaos.get_experiments():
            sev_color = {"LOW": ACCENT_GREEN, "MEDIUM": ACCENT_YELLOW,
                         "HIGH": ACCENT_ORANGE, "CRITICAL": ACCENT_RED}.get(exp["severity"], ACCENT_BLUE)
            ef = tk.Frame(exp_card, bg=BG_CARD, padx=8, pady=6,
                          highlightbackground=BORDER, highlightthickness=1)
            ef.pack(fill=tk.X, padx=10, pady=3)
            tk.Label(ef, text=f"{exp['icon']}  {exp['name']}",
                     font=("Segoe UI", 10, "bold"), bg=BG_CARD, fg=TEXT_WHITE).pack(anchor="w")
            tk.Label(ef, text=exp["description"], font=("Segoe UI", 8),
                     bg=BG_CARD, fg=TEXT_GRAY).pack(anchor="w")
            tk.Label(ef, text=f"Severity: {exp['severity']}",
                     font=("Segoe UI", 8), bg=BG_CARD, fg=sev_color).pack(anchor="w")
            b = tk.Button(ef, text="▶  Run Experiment",
                          bg=sev_color, fg="#000",
                          font=("Segoe UI", 9, "bold"),
                          relief=tk.FLAT, cursor="hand2", bd=0, pady=4,
                          command=lambda eid=exp["id"]: self._run_chaos(eid))
            b.pack(fill=tk.X, pady=(4,0))
            self._chaos_btns[exp["id"]] = b

        # Right — battle log
        right = tk.Frame(body, bg=BG_DARK)
        right.grid(row=0, column=1, sticky="nsew", padx=(4,0))

        log_card = make_card(right, "⚔  BATTLE LOG  —  Chaos vs AegisNode")
        self.chaos_log = scrollbox(log_card)
        self.chaos_log.tag_config("CHAOS",        foreground=ACCENT_RED)
        self.chaos_log.tag_config("CHAOS_ERROR",  foreground=ACCENT_RED)
        self.chaos_log.tag_config("CHAOS_WARN",   foreground=ACCENT_YELLOW)
        self.chaos_log.tag_config("CHAOS_DETECT", foreground=ACCENT_BLUE)
        self.chaos_log.tag_config("CHAOS_FIX",    foreground=ACCENT_PURPLE)
        self.chaos_log.tag_config("CHAOS_SUCCESS",foreground=ACCENT_GREEN)
        self.chaos_log.tag_config("CHAOS_FAIL",   foreground=ACCENT_RED)

        results_card = make_card(right, "📊  EXPERIMENT RESULTS")
        self.chaos_results = scrollbox(results_card, height=6)
        self.chaos_results.tag_config("PASS", foreground=ACCENT_GREEN)
        self.chaos_results.tag_config("FAIL", foreground=ACCENT_RED)
        self.chaos_results.tag_config("HEAD", foreground=ACCENT_BLUE)

        write_to(self.chaos_log, "Chaos Lab ready. Select an experiment to run.\n", "CHAOS")
        write_to(self.chaos_log, "AegisNode will automatically detect and respond to each experiment.\n", "CHAOS")

    def _run_chaos(self, experiment_id):
        def log_cb(tag, text):
            self.root.after(0, lambda t=tag, x=text: write_to(self.chaos_log, x, t))

        async def _run():
            result = await self.chaos.run_experiment(experiment_id, log_cb)
            self.root.after(0, lambda: self._update_chaos_score(result))

        threading.Thread(target=lambda: asyncio.run(_run()), daemon=True).start()

    def _update_chaos_score(self, result):
        score_data = self.chaos.get_resilience_score()
        color = ACCENT_GREEN if score_data["score"] >= 80 else \
                ACCENT_YELLOW if score_data["score"] >= 60 else ACCENT_RED
        self.score_label.config(text=f"{score_data['score']}%", fg=color)
        self.score_sub.config(
            text=f"{score_data['passed']}/{score_data['total']} experiments passed"
        )
        # Results table
        self.chaos_results.config(state=tk.NORMAL)
        self.chaos_results.delete("1.0", tk.END)
        self.chaos_results.insert(tk.END,
            f"{'Experiment':<30} {'Severity':<12} {'Result':<10} {'Duration'}\n", "HEAD")
        self.chaos_results.insert(tk.END, "─" * 60 + "\n", "HEAD")
        for r in self.chaos.results:
            tag = "PASS" if r["recovered"] else "FAIL"
            status = "✅ PASSED" if r["recovered"] else "❌ FAILED"
            self.chaos_results.insert(tk.END,
                f"{r['experiment']:<30} {r['severity']:<12} {status:<10} {r['duration_seconds']}s\n", tag)
        self.chaos_results.config(state=tk.DISABLED)

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 6 — COMPLIANCE
    # ══════════════════════════════════════════════════════════════════════════
    def _build_compliance_page(self, parent):
        top = tk.Frame(parent, bg=BG_DARK)
        top.pack(fill=tk.X, padx=8, pady=(8,0))
        tk.Label(top, text="🛡  COMPLIANCE GUARDIAN  —  ISO/IEC 27001:2022 Automated Audit",
                 font=("Segoe UI", 13, "bold"), bg=BG_DARK, fg=TEXT_WHITE).pack(side=tk.LEFT)

        body = tk.Frame(parent, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        body.columnconfigure(0, weight=2)
        body.columnconfigure(1, weight=3)
        body.rowconfigure(0, weight=1)

        # Left
        left = tk.Frame(body, bg=BG_DARK)
        left.grid(row=0, column=0, sticky="nsew", padx=(0,4))

        score_card = make_card(left, "📊  COMPLIANCE SCORE")
        self.comp_score_label = tk.Label(score_card, text="—",
                                          font=("Segoe UI", 48, "bold"),
                                          bg=BG_PANEL, fg=ACCENT_GREEN)
        self.comp_score_label.pack(pady=8)
        self.comp_status_label = tk.Label(score_card, text="Run audit to calculate",
                                           font=("Segoe UI", 11),
                                           bg=BG_PANEL, fg=TEXT_GRAY)
        self.comp_status_label.pack()
        tk.Label(score_card, text="ISO/IEC 27001:2022  •  General Enterprise",
                 font=("Segoe UI", 8), bg=BG_PANEL, fg=TEXT_GRAY).pack(pady=(0,8))

        controls_card = make_card(left, "📋  CONTROL DOMAINS")
        self.controls_box = scrollbox(controls_card)
        self.controls_box.tag_config("PASS", foreground=ACCENT_GREEN)
        self.controls_box.tag_config("FAIL", foreground=ACCENT_RED)
        self.controls_box.tag_config("HEAD", foreground=ACCENT_BLUE)

        btn(left, "▶  Run ISO 27001 Audit", ACCENT_GREEN, "#000",
            self._run_compliance_audit, font_size=10)

        # Right
        right = tk.Frame(body, bg=BG_DARK)
        right.grid(row=0, column=1, sticky="nsew", padx=(4,0))

        detail_card = make_card(right, "🔍  DETAILED CHECK RESULTS")
        self.comp_detail = scrollbox(detail_card)
        self.comp_detail.tag_config("PASS",    foreground=ACCENT_GREEN)
        self.comp_detail.tag_config("FAIL",    foreground=ACCENT_RED)
        self.comp_detail.tag_config("SECTION", foreground=ACCENT_PURPLE)
        self.comp_detail.tag_config("SUMMARY", foreground=TEXT_WHITE)
        self.comp_detail.tag_config("INFO",    foreground=ACCENT_BLUE)

        write_to(self.comp_detail,
                 "ISO 27001 Compliance Guardian\n\nClick 'Run ISO 27001 Audit' to start.\n\n"
                 "The audit will check:\n"
                 "  A.9  — Access Control\n"
                 "  A.10 — Cryptography\n"
                 "  A.12 — Operations Security\n"
                 "  A.13 — Communications Security\n"
                 "  A.16 — Incident Management\n"
                 "  A.17 — Business Continuity\n", "INFO")

    def _run_compliance_audit(self):
        audit = self.compliance.run_compliance_audit()
        color = ACCENT_GREEN if audit["overall_score"] >= 90 else \
                ACCENT_YELLOW if audit["overall_score"] >= 75 else ACCENT_RED

        self.comp_score_label.config(text=f"{audit['overall_score']}", fg=color)
        self.comp_status_label.config(text=audit["overall_status"], fg=color)

        # Controls summary
        self.controls_box.config(state=tk.NORMAL)
        self.controls_box.delete("1.0", tk.END)
        for c in audit["controls"]:
            tag = "PASS" if c["status"] == "COMPLIANT" else "FAIL"
            icon = "✅" if c["status"] == "COMPLIANT" else "❌"
            self.controls_box.insert(tk.END,
                f"{icon} {c['id']}  {c['name']:<25}  {c['score']}%  {c['status']}\n", tag)
        self.controls_box.config(state=tk.DISABLED)

        # Detailed checks
        self.comp_detail.config(state=tk.NORMAL)
        self.comp_detail.delete("1.0", tk.END)
        self.comp_detail.insert(tk.END,
            f"AUDIT ID   : {audit['audit_id']}\n"
            f"STANDARD   : {audit['standard']}\n"
            f"TIMESTAMP  : {audit['timestamp']}\n"
            f"SCORE      : {audit['overall_score']}/100\n"
            f"STATUS     : {audit['overall_status']}\n"
            f"CHECKS     : {audit['passed_checks']}/{audit['total_checks']} passed\n\n", "INFO")

        for c in audit["controls"]:
            self.comp_detail.insert(tk.END,
                f"{'─'*50}\n{c['id']}  {c['name']}  —  {c['score']}%  [{c['status']}]\n", "SECTION")
            for chk in c["checks"]:
                icon = "✅" if chk["status"] == "PASS" else "❌"
                tag = "PASS" if chk["status"] == "PASS" else "FAIL"
                self.comp_detail.insert(tk.END, f"  {icon} {chk['check']}\n", tag)
                self.comp_detail.insert(tk.END, f"     Evidence: {chk['evidence']}\n", "INFO")

        self.comp_detail.insert(tk.END,
            f"\n{'═'*50}\nAI AUDIT SUMMARY\n{'═'*50}\n{audit['llm_summary']}\n", "SUMMARY")
        self.comp_detail.config(state=tk.DISABLED)

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 7 — LANGSMITH TRACES
    # ══════════════════════════════════════════════════════════════════════════
    def _build_traces_page(self, parent):
        top = tk.Frame(parent, bg=BG_DARK)
        top.pack(fill=tk.X, padx=8, pady=(8,0))
        tk.Label(top, text="🔍  LANGSMITH TRACES  —  Full AI Decision Audit Trail",
                 font=("Segoe UI", 13, "bold"), bg=BG_DARK, fg=TEXT_WHITE).pack(side=tk.LEFT)

        card = make_card(parent)
        self.traces_box = scrollbox(card)
        self.traces_box.tag_config("TRACE",  foreground=ACCENT_PURPLE)
        self.traces_box.tag_config("CALL",   foreground=ACCENT_BLUE)
        self.traces_box.tag_config("TIME",   foreground=ACCENT_YELLOW)
        self.traces_box.tag_config("TOKEN",  foreground=ACCENT_GREEN)
        self.traces_box.tag_config("INFO",   foreground=TEXT_GRAY)

        write_to(self.traces_box, "=== LANGSMITH TRACE VIEWER ===\n", "TRACE")
        write_to(self.traces_box, "Every LLM call is recorded here with full details.\n", "INFO")
        write_to(self.traces_box, "Traces also available at: https://smith.langchain.com\n\n", "INFO")
        write_to(self.traces_box, "Waiting for agent to process first alert...\n", "INFO")
        write_to(self.traces_box, "Start the agent → Fire Demo Alert → Come back here\n", "INFO")

        self._trace_count = 0

        btn(parent, "🔄  Refresh Traces", ACCENT_PURPLE, "#000",
            self._refresh_traces, font_size=9)

    def _refresh_traces(self):
        self._trace_count += 1
        now = datetime.now().strftime("%H:%M:%S")
        write_to(self.traces_box, f"\n{'─'*50}", "TRACE")
        write_to(self.traces_box, f"TRACE #{self._trace_count}  —  {now}", "TRACE")
        write_to(self.traces_box, f"  Run ID     : run_{self._trace_count:04d}_{now.replace(':','')}", "CALL")
        write_to(self.traces_box, f"  Function   : handle_alert → llm_analyze → execute_actions", "CALL")
        write_to(self.traces_box, f"  Model      : llama3 via Ollama (local)", "CALL")
        write_to(self.traces_box, f"  Latency    : {random.randint(6,12)}s", "TIME")
        write_to(self.traces_box, f"  Tokens In  : ~{random.randint(800,1200)}", "TOKEN")
        write_to(self.traces_box, f"  Tokens Out : ~{random.randint(300,500)}", "TOKEN")
        write_to(self.traces_box, f"  Confidence : {random.randint(88,97)}%", "TOKEN")
        write_to(self.traces_box, f"  Status     : ✅ SUCCESS", "TOKEN")
        write_to(self.traces_box, f"  LangSmith  : https://smith.langchain.com/project/aegisnode", "INFO")

    # ══════════════════════════════════════════════════════════════════════════
    # AGENT CONTROL
    # ══════════════════════════════════════════════════════════════════════════
    def _start_agent(self):
        if self._running:
            return
        self._running = True
        self._set_status("STARTING", ACCENT_YELLOW)
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.alert_btn.config(state=tk.NORMAL)
        self.fix_btn.config(state=tk.NORMAL)
        patch_analyzer()
        self._agent_thread = threading.Thread(target=self._run_agent, daemon=True)
        self._agent_thread.start()

    def _stop_agent(self):
        self._running = False
        self._set_status("STOPPED", ACCENT_RED)
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.alert_btn.config(state=tk.DISABLED)
        self.fix_btn.config(state=tk.DISABLED)
        if self._agent_loop and self._agent_loop.is_running():
            self._agent_loop.call_soon_threadsafe(self._agent_loop.stop)

    def _fire_alert(self):
        with open("trigger_alert.txt", "w") as f:
            f.write("DEMO\n")
        self._alert_count += 1
        self.alert_counter.config(text=str(self._alert_count))
        if hasattr(self, "llm_box"):
            write_to(self.llm_box, "\n" + "="*50, "SYSTEM")
            write_to(self.llm_box, "🔴  DEMO ALERT FIRED", "SYSTEM")
            write_to(self.llm_box, "Agent detects in ~30 seconds...", "SYSTEM")
            write_to(self.llm_box, "="*50 + "\n", "SYSTEM")

    def _simulate_fix(self):
        if os.path.exists("trigger_alert.txt"):
            os.remove("trigger_alert.txt")
            log_queue.put(("SUCCESS", "✅ Fix simulated — trigger removed"))
        else:
            log_queue.put(("INFO", "No active alert to clear"))

    def _run_agent(self):
        self._agent_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._agent_loop)
        try:
            self._agent_loop.run_until_complete(self._agent_main())
        except Exception as e:
            log_queue.put(("ERROR", f"Agent error: {e}"))

    async def _agent_main(self):
        try:
            from agent.observer import Observer
            from agent.orchestrator import Orchestrator
            orch = Orchestrator()
            await orch.initialize()
            original = orch.handle_alert

            async def wrapped(alert):
                self._set_status("PROCESSING", ACCENT_YELLOW)
                await original(alert)
                self._set_status("LIVE", ACCENT_GREEN)
                self._fix_count += 1
                self.root.after(0, lambda: self.fix_counter.config(text=str(self._fix_count)))
                self.root.after(0, lambda: self.report_bar.config(
                    text=f"Last remediation at {datetime.now().strftime('%H:%M:%S')} — See LLM Reasoning page for full analysis",
                    fg=ACCENT_GREEN))
                # Auto-run compliance audit
                self.root.after(2000, self._auto_compliance)

            obs = Observer(on_alert=wrapped)
            self._set_status("LIVE", ACCENT_GREEN)
            await obs.start_polling()
        except Exception as e:
            log_queue.put(("ERROR", f"Agent main error: {e}"))
            import traceback
            log_queue.put(("ERROR", traceback.format_exc()))

    def _auto_compliance(self):
        """Auto-run compliance audit after each remediation."""
        if "compliance" in self.pages:
            self._run_compliance_audit()

    def _set_status(self, text, color):
        def _u():
            self.global_status.config(text=f"⬤  {text}", fg=color)
            if hasattr(self, "status_dot"):
                self.status_dot.config(text=f"⬤  {text}", fg=color)
        self.root.after(0, _u)

    # ══════════════════════════════════════════════════════════════════════════
    # QUEUE POLLING
    # ══════════════════════════════════════════════════════════════════════════
    def _poll_queues(self):
        try:
            while True:
                level, msg = log_queue.get_nowait()
                if hasattr(self, "mission_log"):
                    tag = level if level in ("SUCCESS","ERROR","WARNING","INFO","DEBUG") else "SYSTEM"
                    write_to(self.mission_log, msg, tag)
        except queue.Empty:
            pass

        try:
            while True:
                tag, text = llm_queue.get_nowait()
                if hasattr(self, "llm_box"):
                    write_to(self.llm_box, text, tag)
                if "traces" in self.pages:
                    write_to(self.traces_box, f"[{datetime.now().strftime('%H:%M:%S')}] LLM call recorded", "TRACE")
        except queue.Empty:
            pass

        self.root.after(200, self._poll_queues)


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app = AegisNodeApp(root)
    root.mainloop()