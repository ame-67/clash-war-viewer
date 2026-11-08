# -*- coding: utf-8 -*-
"""
部落冲突(国际服) 部落战成员战斗情况查看器
==========================================
数据来源: Clash of Clans 官方 API (developer.clashofclans.com)

功能:
  1. 查看当前部落战(战斗日/准备日/已结束)中每一位成员的战斗情况
     - 进攻: 次数 / 总星 / 总摧毁率 / 场均星 / 最佳进攻
     - 防守: 被攻星数 / 被摧毁率 / 未进攻次数
     - 双击成员行可查看该成员每一次进攻与防守的明细
  2. 查看部落对战联赛(CWL)每一轮及全部轮次汇总的成员数据
  3. 查看部落战争日志(汇总信息)
  4. 一键导出当前表格为 CSV(Excel 可直接打开)

使用前提: 需要一个 Clash of Clans 开发者 API 令牌,
见 developer.clashofclans.com (点击程序内"帮助"按钮查看详细步骤)。
"""

import csv
import json
import os
import queue
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

API_BASE = "https://api.clashofclans.com/v1"
APP_NAME = "CoCWarViewer"
TAG_CHARS = "0289PYLQGRJCUV"          # 部落冲突标签可用字符
CN_TZ = timezone(timedelta(hours=8))  # 北京时间

STATE_CN = {
    "preparation": "准备日",
    "inWar": "战斗日",
    "warEnded": "已结束",
    "notInWar": "无战争",
    "ended": "已结束",
}

ROLE_CN = {
    "leader": "首领",
    "coLeader": "副首领",
    "admin": "长老",
    "elder": "长老",
    "member": "成员",
}

CAPITAL_STATE_CN = {
    "ongoing": "进行中",
    "inProgress": "进行中",
    "ended": "已结束",
}

# 活跃度档位(天): 关注 / 警告 / 严重
ACTIVITY_WARN_DAYS = 7
ACTIVITY_ALERT_DAYS = 14
ACTIVITY_SEVERE_DAYS = 30

# 活跃度快照的自动记录间隔(秒): 自动刷新时最多每 5 分钟记录一次
SNAPSHOT_MIN_INTERVAL = 300


# ---------------------------------------------------------------- 工具函数

def resource_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def data_dir():
    base = os.environ.get("APPDATA") or resource_dir()
    d = os.path.join(base, APP_NAME)
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        d = resource_dir()
    return d


def config_file():
    return os.path.join(data_dir(), "config.json")


def activity_file():
    return os.path.join(data_dir(), "activity.json")


def load_activity():
    """本地活跃度数据: {"members": {tag: {...}}, "whitelist": [tag, ...]}"""
    try:
        with open(activity_file(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("members", {})
            data.setdefault("whitelist", [])
            return data
    except Exception:
        pass
    return {"members": {}, "whitelist": []}


def save_activity(data):
    try:
        with open(activity_file(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


# ---------------------------------------------------------------- 都城突袭历史
# 官方 API 只对最新一次突袭返回成员明细, 历史赛季成员为空;
# 因此每次突袭期间查询时, 把成员刀数快照存到本地, 下次即可对比"上次"。

CAPITAL_HISTORY_MAX = 8


def capital_history_file():
    return os.path.join(data_dir(), "capital_history.json")


def load_capital_history():
    """{"seasons": {startTime: {start, end, members: {tag: {name, attacks, limit}}}}}"""
    try:
        with open(capital_history_file(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("seasons"), dict):
            return data
    except Exception:
        pass
    return {"seasons": {}}


def save_capital_history(data):
    try:
        with open(capital_history_file(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def update_capital_history(season):
    """把一次突袭的成员刀数写入本地历史(覆盖同一赛季, 保留最新快照)"""
    members = season.get("members") or []
    key = str(season.get("startTime") or season.get("endTime") or "")
    if not key or not members:
        return load_capital_history()
    hist = load_capital_history()
    entry = hist["seasons"].setdefault(key, {})
    entry["start"] = season.get("startTime")
    entry["end"] = season.get("endTime")
    mem = entry.setdefault("members", {})
    for m in members:
        tag = clean_tag(m.get("tag", ""))
        if not tag:
            continue
        mem[tag] = {
            "name": m.get("name"),
            "attacks": int(m.get("attacks") or 0),
            "limit": int(m.get("attackLimit") or 0) + int(m.get("bonusAttackLimit") or 0),
        }
    keys = sorted(hist["seasons"].keys(), reverse=True)
    for k in keys[CAPITAL_HISTORY_MAX:]:
        hist["seasons"].pop(k, None)
    save_capital_history(hist)
    return hist


def load_config():
    try:
        with open(config_file(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    try:
        with open(config_file(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def clean_tag(tag):
    """规范化部落标签: 去 #、转大写、字母O视作数字0"""
    t = (tag or "").strip().upper().replace("O", "0")
    if t.startswith("#"):
        t = t[1:]
    return t


def url_tag(tag):
    return urllib.parse.quote("#" + clean_tag(tag), safe="")


def update_snapshots(members, activity, war=None, now=None, side_tag=None):
    """用一次成员列表(以及可选的战争数据)更新本地活跃度快照。

    活跃判定(近似):
      - 捐兵/收兵数量增加(每周清零导致的减少不算)
      - 经验等级、大本等级变化
      - 同一场部落战中进攻次数增加
    返回更新后的 activity。"""
    now = now or time.time()
    old = activity.get("members") or {}
    new = {}
    war_key = ""
    war_attacks = {}
    if war and war.get("state") in ("preparation", "inWar", "warEnded"):
        war_key = str(war.get("preparationStartTime") or war.get("startTime") or "")
        clan = war.get("clan") or {}
        opp = war.get("opponent") or {}
        side = clan
        if side_tag:
            st = clean_tag(side_tag)
            if clean_tag(opp.get("tag", "")) == st and clean_tag(clan.get("tag", "")) != st:
                side = opp
        for m in side.get("members") or []:
            t = clean_tag(m.get("tag", ""))
            if t:
                war_attacks[t] = len(m.get("attacks") or [])

    for m in members or []:
        tag = clean_tag(m.get("tag", ""))
        if not tag:
            continue
        fp = {k: m.get(k) for k in ("donations", "donationsReceived", "expLevel", "townHallLevel")}
        rec = old.get(tag)
        if not isinstance(rec, dict):
            rec = {"last_change": now, "values": fp, "first_seen": now}
        else:
            prev = rec.get("values") or {}
            changed = False
            for k, v in fp.items():
                pv = prev.get(k)
                if v is None or pv is None:
                    if v != pv:
                        changed = True
                    continue
                if k in ("donations", "donationsReceived"):
                    if v > pv:          # 每周清零(减少)不算活跃
                        changed = True
                elif v != pv:
                    changed = True
            rec["values"] = fp

            if war_attacks and tag in war_attacks:
                cnt = war_attacks[tag]
                prev_war = rec.get("war") or {}
                if prev_war.get("key") == war_key:
                    if cnt > int(prev_war.get("count") or 0):
                        changed = True
                rec["war"] = {"key": war_key, "count": cnt}

            if changed:
                rec["last_change"] = now

        rec["name"] = m.get("name")
        rec["role"] = m.get("role")
        rec["th"] = m.get("townHallLevel")
        rec["trophies"] = m.get("trophies")
        rec["donations"] = m.get("donations")
        rec.setdefault("first_seen", now)
        rec["last_checked"] = now
        new[tag] = rec

    activity["members"] = new
    return activity


def api_get(path, token, retries=3):
    """调用 Clash of Clans API, 429 限流时自动重试"""
    url = API_BASE + path
    last = None
    for i in range(retries):
        req = urllib.request.Request(url, headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429 and i < retries - 1:
                time.sleep(2.0)
                continue
            break
        except urllib.error.URLError as e:
            last = e
            if i < retries - 1:
                time.sleep(1.0)
                continue
            break
    raise last


def api_error_message(e):
    """把网络异常翻译成友好提示"""
    if isinstance(e, urllib.error.HTTPError):
        code = e.code
        if code == 403:
            return ("API令牌无效或来源IP未授权(403)。\n"
                    "请在 developer.clashofclans.com 重新创建令牌,\n"
                    "并填写你当前电脑的公网IP。")
        if code == 404:
            return "未找到该部落(404),请检查部落标签是否输入正确(例如 #2LJQ2YVY)。"
        if code == 429:
            return "请求过于频繁(429),API被限流,请稍后再试。"
        return "HTTP 错误 %s" % code
    if isinstance(e, urllib.error.URLError):
        return "网络错误,无法连接 Clash of Clans API。\n请检查网络/代理设置。"
    return "未知错误: %s" % e


def fmt_cn_time(s):
    """API 时间转北京时间 (MM-DD HH:MM)"""
    try:
        dt = datetime.strptime(s[:14], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        return dt.astimezone(CN_TZ).strftime("%m-%d %H:%M")
    except Exception:
        return s or "-"


def fmt_date(s):
    try:
        dt = datetime.strptime(s[:14], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        return dt.astimezone(CN_TZ).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return s or "-"


def fmt_ts_local(ts):
    """Unix 时间戳 -> 本地时间字符串"""
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "-"


def fmt_dur(sec):
    try:
        sec = int(sec)
    except Exception:
        return "-"
    return "%d分%02d秒" % (sec // 60, sec % 60)


def fmt_pct(v):
    """摧毁率格式化: 官方可能返回 98.2 / 342.33334 之类, 统一保留1位小数"""
    try:
        return "%.1f" % float(v)
    except Exception:
        return str(v) if v is not None else "0"


# ---------------------------------------------------------------- 数据统计

def collect_side(wars, side_tag):
    """把多场战争中指定一方的成员数据按成员聚合。
    返回 (agg, 应打总次数)

    说明: 官方 API 中成员的 opponentAttacks 只是整数(被攻击次数),
    防守明细需从双方所有进攻记录中按 defenderTag 反查得到。"""
    agg = {}
    apm_sum = 0
    for w in wars:
        clan = w.get("clan") or {}
        opp = w.get("opponent") or {}
        side = clan if clean_tag(clan.get("tag", "")) == side_tag else opp
        apm_sum += int(w.get("attacksPerMember") or 1)

        # 收集本场双方的全部进攻, 用于反查"谁打了我"
        all_attacks = []
        for s in (clan, opp):
            for m in s.get("members") or []:
                all_attacks.extend(m.get("attacks") or [])
        defs_by_member = {}
        for a in all_attacks:
            dt = clean_tag(a.get("defenderTag", ""))
            if dt:
                defs_by_member.setdefault(dt, []).append(a)

        for m in side.get("members") or []:
            t = clean_tag(m.get("tag", ""))
            if not t:
                continue
            if t not in agg:
                agg[t] = {
                    "name": m.get("name", ""),
                    "th": m.get("townhallLevel", 0),
                    "pos": m.get("mapPosition", 0),
                    "attacks": [],
                    "defs": [],
                }
            agg[t]["attacks"].extend(m.get("attacks") or [])
            agg[t]["defs"].extend(defs_by_member.get(t, []))
    return agg, apm_sum


def make_rows(agg, apm_sum):
    rows = []
    for t, d in agg.items():
        attacks = d["attacks"]
        defs = d["defs"]
        n = len(attacks)
        stars = sum(int(a.get("stars") or 0) for a in attacks)
        dest = sum(int(a.get("destructionPercentage") or 0) for a in attacks)
        best = max(attacks,
                   key=lambda a: (int(a.get("stars") or 0), int(a.get("destructionPercentage") or 0)),
                   default=None)
        def_stars = sum(int(a.get("stars") or 0) for a in defs)
        def_dest = sum(int(a.get("destructionPercentage") or 0) for a in defs)
        rows.append({
            "pos": d["pos"],
            "name": d["name"],
            "th": d["th"],
            "n": n,
            "stars": stars,
            "dest": dest,
            "avg": round(stars / n, 2) if n else 0,
            "best_stars": int(best.get("stars") or 0) if best else None,
            "best_dest": int(best.get("destructionPercentage") or 0) if best else None,
            "def_stars": def_stars,
            "def_dest": def_dest,
            "exp": apm_sum,
            "missed": max(0, apm_sum - n),
            "attacks": attacks,
            "defs": defs,
        })
    rows.sort(key=lambda r: r["pos"] if isinstance(r["pos"], int) else 10 ** 9)
    return rows


# ---------------------------------------------------------------- 主界面

class App:
    def __init__(self, root):
        self.root = root
        root.title("部落冲突(国际服) 部落战成员战斗情况查看器")
        root.geometry("1360x700")
        root.minsize(1080, 580)
        try:
            if getattr(sys, "frozen", False):
                root.iconbitmap(default=sys.executable)
        except Exception:
            pass

        self.cfg = load_config()
        self.wars = []            # 当前加载的战争数据(1场 或 汇总时的多场)
        self.round_wars = []      # CWL 各轮战争
        self.sel_map = {}         # 轮次下拉框 label -> 轮次索引或'agg'
        self.agg_mode = False
        self.busy = False
        self.rows = []
        self.tag_name = {}
        self.last_mode = None
        self.clan_tag = ""
        self.cwl_season = ""
        self.q = queue.Queue()      # 后台线程 -> 主线程 的任务队列
        self._poll_job = None
        self.paused = False          # 是否暂停自动刷新
        self.auto_refresh_job = None # 自动刷新的 after 任务 id
        self.refresh_interval = 30000  # 自动刷新间隔(毫秒) = 30秒
        self.activity_data = load_activity()   # 本地活跃度快照
        self.activity_win = None               # 活跃度窗口
        self._last_snapshot_ts = 0.0           # 上次记录快照的时间
        self.capital_win = None                # 都城窗口
        self.capital_seasons = []              # 都城赛季数据
        self.capital_sel = None
        self.capital_table = None
        self.capital_summary = None

        self.build_ui()
        self.render()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.show_hint("提示: 填写 API 令牌和部落标签后,点击“查询当前部落战”或“部落联赛CWL”。")
        self._poll()
        self.root.after(400, self.auto_query)

    # ------------------------------------------------ UI 构建

    def build_ui(self):
        root = self.root
        top = ttk.Frame(root, padding=(10, 8, 10, 4))
        top.pack(fill="x")

        ttk.Label(top, text="API令牌:").pack(side="left")
        self.token_entry = ttk.Entry(top, width=34, show="*")
        self.token_entry.insert(0, self.cfg.get("token", ""))
        self.token_entry.pack(side="left", padx=(4, 14))

        ttk.Label(top, text="部落标签:").pack(side="left")
        self.tag_entry = ttk.Entry(top, width=13)
        self.tag_entry.insert(0, self.cfg.get("clan_tag", ""))
        self.tag_entry.pack(side="left", padx=(4, 14))

        self.buttons = []
        self.pause_btn = None
        for text, cmd in (
            ("查询当前部落战", self.query_current),
            ("部落联赛CWL", self.query_cwl),
            ("战争日志", self.query_warlog),
            ("部落都城", self.query_capital),
            ("活跃度", self.open_activity),
            ("刷新", self.refresh),
            ("暂停刷新", self.toggle_pause),
            ("导出CSV", self.export_csv),
            ("帮助", self.show_help),
        ):
            b = ttk.Button(top, text=text, command=cmd)
            b.pack(side="left", padx=2)
            self.buttons.append(b)
            if text == "暂停刷新":
                self.pause_btn = b

        help_text = ("令牌获取: developer.clashofclans.com → 用谷歌账号等登录 → Create Key → "
                     "填写你电脑的公网IP → 勾选 Clash of Clans → 复制令牌粘贴到这里。"
                     "标签示例: #2LJQ2YVY (带#或不带均可)。")
        ttk.Label(root, text=help_text, foreground="#666666", wraplength=1340,
                  justify="left").pack(fill="x", padx=10, pady=(0, 4))

        sel = ttk.Frame(root, padding=(10, 0, 10, 4))
        sel.pack(fill="x")
        ttk.Label(sel, text="轮次:").pack(side="left")
        self.sel = ttk.Combobox(sel, state="disabled", width=26)
        self.sel.pack(side="left", padx=(4, 16))
        self.sel.bind("<<ComboboxSelected>>", self.on_select)

        self.side_var = tk.StringVar(value="")
        self.rb_me = ttk.Radiobutton(sel, text="我方", variable=self.side_var,
                                     value="", command=self.on_side_change, state="disabled")
        self.rb_me.pack(side="left", padx=4)
        self.rb_opp = ttk.Radiobutton(sel, text="敌方", variable=self.side_var,
                                      value="", command=self.on_side_change, state="disabled")
        self.rb_opp.pack(side="left", padx=4)

        self.info_label = ttk.Label(sel, text="", foreground="#0a58a0",
                                    wraplength=680, justify="left")
        self.info_label.pack(side="left", padx=12)

        # 成员数据表
        table_frame = ttk.Frame(root)
        table_frame.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        cols = ("pos", "name", "th", "n", "stars", "dest", "avg", "best",
                "def_stars", "def_dest", "exp", "missed")
        headings = {
            "pos": "位置", "name": "成员", "th": "大本", "n": "进攻次数",
            "stars": "总星数", "dest": "总摧毁%", "avg": "场均星",
            "best": "最佳进攻", "def_stars": "被攻星数", "def_dest": "被摧毁%",
            "exp": "应打次数", "missed": "未进攻",
        }
        widths = {"pos": 50, "name": 150, "th": 60, "n": 80, "stars": 80,
                  "dest": 90, "avg": 70, "best": 110, "def_stars": 80,
                  "def_dest": 90, "exp": 80, "missed": 80}
        self.table = ttk.Treeview(table_frame, columns=cols, show="headings")
        for c in cols:
            self.table.heading(c, text=headings[c])
            self.table.column(c, width=widths[c], anchor="center")
        self.table.column("name", anchor="w")
        ys = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        xs = ttk.Scrollbar(table_frame, orient="horizontal", command=self.table.xview)
        self.table.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.table.bind("<Double-1>", self.on_double)

        self.table.tag_configure("green", background="#d6f2d6")
        self.table.tag_configure("orange", background="#fdeecb")
        self.table.tag_configure("red", background="#f8d3d3")
        self.table.tag_configure("none", background="#f2f2f2")

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(root, textvariable=self.status_var, relief="sunken",
                  anchor="w", padding=(8, 2)).pack(fill="x", side="bottom")

    # ------------------------------------------------ 通用逻辑

    def set_status(self, text):
        self.status_var.set(text)

    def check_inputs(self):
        token = self.token_entry.get().strip()
        tag = clean_tag(self.tag_entry.get())
        if not token or not tag:
            messagebox.showwarning("提示", "请先填写 API令牌 和 部落标签(如 #2LJQ2YVY)。")
            return None, None
        if re.fullmatch(r"[%s]{3,12}" % TAG_CHARS, tag) is None:
            if not messagebox.askyesno("确认", "部落标签“%s”看起来不太像标准标签。\n仍然继续查询吗？" % tag):
                return None, None
        return tag, token

    def save_inputs(self):
        self.cfg["token"] = self.token_entry.get().strip()
        self.cfg["clan_tag"] = self.tag_entry.get().strip()
        save_config(self.cfg)

    def run_async(self, fn):
        """在工作线程里执行网络请求; UI 操作一律通过队列回到主线程"""
        if self.busy:
            return
        self.busy = True
        self.set_status("正在请求 Clash of Clans API ...")
        for b in self.buttons:
            b.config(state="disabled")

        def runner():
            try:
                fn()
            except Exception as exc:      # 兜底: 绝不让后台线程静默崩溃
                self.q.put(("error", "程序内部错误: %s" % exc))
            finally:
                self.q.put(("done", None))

        threading.Thread(target=runner, daemon=True).start()

    def _poll(self):
        """主线程轮询队列(tkinter 只能在主线程操作,这里保证线程安全)"""
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "done":
                    self.on_async_done()
                elif kind == "call":
                    try:
                        payload()
                    except Exception as exc:   # UI 更新异常不能静默吞掉
                        self.show_error("界面更新出错:\n%s" % exc)
                elif kind == "error":
                    self.show_error(payload)
        except queue.Empty:
            pass
        try:
            self._poll_job = self.root.after(80, self._poll)
        except tk.TclError:
            pass

    def on_async_done(self):
        self.busy = False
        for b in self.buttons:
            b.config(state="normal")
        if self.status_var.get().startswith("正在请求"):
            self.set_status("就绪")
        self.schedule_auto_refresh()

    def schedule_auto_refresh(self):
        """安排下一次自动刷新(仅当前部落战视图;暂停时不安排)"""
        if self.auto_refresh_job is not None:
            try:
                self.root.after_cancel(self.auto_refresh_job)
            except Exception:
                pass
            self.auto_refresh_job = None
        if not self.paused and self.last_mode == "current":
            self.auto_refresh_job = self.root.after(self.refresh_interval, self._auto_tick)

    def _auto_tick(self):
        self.auto_refresh_job = None
        if self.paused:
            return
        if self.busy:
            self.schedule_auto_refresh()
            return
        if self.last_mode == "current":
            self.query_current(silent=True)
        else:
            self.schedule_auto_refresh()

    def toggle_pause(self):
        """暂停/恢复自动刷新"""
        self.paused = not self.paused
        if self.paused:
            self.pause_btn.config(text="继续刷新")
            self.schedule_auto_refresh()   # 取消已排队的自动刷新
            self.set_status("已暂停自动刷新,当前数据保持不变;点“继续刷新”恢复")
        else:
            self.pause_btn.config(text="暂停刷新")
            self.schedule_auto_refresh()
            self.set_status("已恢复自动刷新(每30秒)")

    def post(self, fn):
        """工作线程里调用: 把 UI 操作投递到主线程执行"""
        self.q.put(("call", fn))

    def show_error(self, msg):
        self.info_label.config(text=msg.splitlines()[0] if msg else "查询失败",
                               foreground="#b00020")
        self.set_status("查询失败")
        messagebox.showerror("错误", msg)

    def show_notice(self, msg, dialog=True):
        self.info_label.config(text=msg, foreground="#c26a00")
        self.set_status("就绪")
        if dialog:
            messagebox.showinfo("提示", msg)

    def silent_error(self, msg):
        """自动刷新失败时: 只在窗口内提示,不弹窗"""
        first = msg.splitlines()[0] if msg else "自动刷新失败"
        self.info_label.config(text=first, foreground="#b00020")
        self.set_status("自动刷新失败: " + first[:30])

    def show_hint(self, msg):
        self.info_label.config(text=msg, foreground="#666666")

    def on_close(self):
        try:
            if self._poll_job is not None:
                self.root.after_cancel(self._poll_job)
        except Exception:
            pass
        self.root.destroy()


    def oriented_sides(self, w):
        """返回 (我方, 敌方)"""
        clan = w.get("clan") or {}
        opp = w.get("opponent") or {}
        if clean_tag(clan.get("tag", "")) == self.clan_tag:
            return clan, opp
        return opp, clan

    # ------------------------------------------------ 查询入口

    def query_current(self, silent=False):
        tag, token = self.check_inputs()
        if not tag:
            return
        self.clan_tag = tag
        self.last_mode = "current"
        self.save_inputs()

        def work():
            try:
                war = api_get("/clans/%s/currentwar" % url_tag(tag), token)
            except Exception as e:
                msg = "获取当前部落战失败:\n" + api_error_message(e)
                if silent:
                    self.post(lambda m=msg: self.silent_error(m))
                else:
                    self.post(lambda m=msg: self.show_error(m))
                return
            if war.get("state") == "notInWar":
                def empty():
                    self.show_empty()
                    self.show_notice("当前没有进行中的部落战。\n若现在是联赛期间,请点击“部落联赛CWL”查看联赛。",
                                     dialog=not silent)
                self.post(empty)
            else:
                self.post(lambda w=war: self.show_wars([w]))
            # 记录活跃度快照(自动刷新时每5分钟最多一次, 手动查询立即记录)
            self.try_snapshot(tag, token, war, silent)

        self.run_async(work)

    def query_cwl(self, silent=False):
        tag, token = self.check_inputs()
        if not tag:
            return
        self.clan_tag = tag
        self.last_mode = "cwl"
        self.save_inputs()

        def work():
            self.try_snapshot(tag, token, None, silent)
            try:
                lg = api_get("/clans/%s/currentwar/leaguegroup" % url_tag(tag), token)
            except urllib.error.HTTPError as e:
                if e.code == 404:      # 404 = 该部落没有参加联赛
                    def not_in_cwl():
                        self.show_empty()
                        self.show_notice("该部落当前未参加部落对战联赛(联赛每月1~8日进行)。\n请点击“查询当前部落战”查看常规部落战。",
                                         dialog=not silent)
                    self.post(not_in_cwl)
                else:
                    msg = "获取联赛信息失败:\n" + api_error_message(e)
                    if silent:
                        self.post(lambda m=msg: self.silent_error(m))
                    else:
                        self.post(lambda m=msg: self.show_error(m))
                return
            except Exception as e:
                msg = "获取联赛信息失败:\n" + api_error_message(e)
                if silent:
                    self.post(lambda m=msg: self.silent_error(m))
                else:
                    self.post(lambda m=msg: self.show_error(m))
                return
            state = lg.get("state")
            rounds = lg.get("rounds") or []
            if state == "preparation":
                def prep():
                    self.show_empty()
                    self.show_notice("联赛处于准备阶段,尚无对战数据可查看。", dialog=not silent)
                self.post(prep)
                return
            if not rounds:
                def off():
                    self.show_empty()
                    self.show_notice("当前不在部落对战联赛期(联赛每月1~8日进行),\n官方API不提供往届联赛数据。",
                                     dialog=not silent)
                self.post(off)
                return
            wars = []
            failed = None
            for r in rounds:
                for wt in (r.get("warTags") or []):
                    try:
                        w = api_get("/clanwarleagues/wars/%s" % url_tag(wt), token)
                    except Exception as e:
                        failed = e
                        continue
                    side_tags = {clean_tag((w.get("clan") or {}).get("tag", "")),
                                 clean_tag((w.get("opponent") or {}).get("tag", ""))}
                    if tag in side_tags:
                        wars.append(w)
                time.sleep(0.3)
            if not wars:
                if failed is not None:
                    msg = "获取联赛对战数据失败:\n" + api_error_message(failed)
                    self.post(lambda m=msg: self.show_error(m))
                else:
                    def none_found():
                        self.show_empty()
                        self.show_notice("未找到本部落的联赛对战数据。")
                    self.post(none_found)
                return
            labels, sel_map = [], {}
            for i, w in enumerate(wars):
                me, other = self.oriented_sides(w)
                label = "第%d轮 vs %s" % (i + 1, other.get("name") or "?")
                sel_map[label] = i
                labels.append(label)
            if len(wars) > 1:
                sel_map["汇总(全部轮次)"] = "agg"
                labels.append("汇总(全部轮次)")
            season = lg.get("season") or ""
            self.post(lambda: self.show_cwl(wars, labels, sel_map, season))

        self.run_async(work)

    def query_warlog(self):
        tag, token = self.check_inputs()
        if not tag:
            return
        self.clan_tag = tag
        self.last_mode = "warlog"
        self.save_inputs()

        def work():
            try:
                log = api_get("/clans/%s/warlog?limit=30" % url_tag(tag), token)
            except Exception as e:
                msg = "获取战争日志失败:\n" + api_error_message(e)
                self.post(lambda m=msg: self.show_error(m))
                return
            self.post(lambda: self.show_warlog(log.get("items") or []))

        self.run_async(work)

    def refresh(self):
        if self.last_mode == "current":
            self.query_current()
        elif self.last_mode == "cwl":
            self.query_cwl()
        elif self.last_mode == "warlog":
            self.query_warlog()
        elif self.last_mode == "capital":
            self.query_capital()
        else:
            messagebox.showinfo("提示", "尚未查询过,请先点击查询按钮。")

    def auto_query(self):
        """启动时若已保存令牌与标签,自动查询一次当前部落战"""
        if self.busy:
            return
        if self.token_entry.get().strip() and self.tag_entry.get().strip():
            self.query_current(silent=True)

    # ------------------------------------------------ 结果展示

    def show_wars(self, wars):
        self.round_wars = []
        self.wars = wars
        self.agg_mode = False
        self.sel.config(values=[], state="disabled")
        self.update_sides()
        self.render()

    def show_cwl(self, wars, labels, sel_map, season):
        self.cwl_season = season
        self.round_wars = wars
        self.sel_map = sel_map
        self.agg_mode = False
        self.sel.config(values=labels, state="readonly")
        self.sel.current(0)
        self.wars = [wars[0]]
        self.update_sides()
        self.render()

    def show_warlog(self, items):
        """战争日志窗口(官方只给胜负汇总, 没有成员明细)"""
        win = tk.Toplevel(self.root)
        win.title("部落战争日志")
        win.geometry("900x540")
        win.minsize(700, 380)

        note = ("提示: 官方API不提供常规部落战的历史成员明细。\n"
                "成员明细请在战斗日/战争刚结束时用“查询当前部落战”查看;联赛成员明细请用“部落联赛CWL”。")
        ttk.Label(win, text=note, foreground="#666666",
                  wraplength=860, justify="left").pack(anchor="w", padx=12, pady=(10, 2))

        if not items:
            ttk.Label(win, text="该部落暂无战争日志记录。").pack(anchor="w", padx=12, pady=10)
            return

        frame = ttk.Frame(win)
        frame.pack(fill="both", expand=True, padx=12, pady=8)
        cols = ("date", "result", "opp", "stars", "ostars", "size", "dest", "odest")
        heads = {"date": "结束时间", "result": "结果", "opp": "对手",
                 "stars": "我方星", "ostars": "敌方星", "size": "规模",
                 "dest": "我方摧毁%", "odest": "敌方摧毁%"}
        tv = ttk.Treeview(frame, columns=cols, show="headings")
        for c in cols:
            tv.heading(c, text=heads[c])
            tv.column(c, width=100, anchor="center")
        ys = ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=ys.set)
        tv.pack(side="left", fill="both", expand=True)
        ys.pack(side="right", fill="y")

        tv.tag_configure("win", background="#d6f2d6")
        tv.tag_configure("lose", background="#f8d3d3")
        tv.tag_configure("tie", background="#fdeecb")

        res_cn = {"win": "胜利", "lose": "失败", "tie": "平局"}
        for it in items:
            me, other = self.oriented_sides(it)
            result = it.get("result")
            tv.insert("", "end", tags=(result or "tie",), values=(
                fmt_date(it.get("endTime")),
                res_cn.get(result, result or "-"),
                other.get("name") or "-",
                me.get("stars") or 0,
                other.get("stars") or 0,
                it.get("teamSize") or "-",
                fmt_pct(me.get("destructionPercentage")),
                fmt_pct(other.get("destructionPercentage")),
            ))

    # ------------------------------------------------ 成员活跃度(离线追踪)

    def try_snapshot(self, tag, token, war=None, silent=False):
        """后台线程中记录一次成员活跃度快照(失败不影响主流程)"""
        now = time.time()
        if silent and now - self._last_snapshot_ts < SNAPSHOT_MIN_INTERVAL:
            return
        try:
            ms = api_get("/clans/%s/members?limit=50" % url_tag(tag), token)
            act = load_activity()
            update_snapshots(ms.get("items") or [], act, war=war, side_tag=tag)
            save_activity(act)
            self._last_snapshot_ts = time.time()
            self.post(lambda a=act: self.apply_activity(a))
        except Exception:
            pass

    def apply_activity(self, act):
        self.activity_data = act
        self.render_activity()

    def open_activity(self):
        if self.activity_win is not None and self.activity_win.winfo_exists():
            self.activity_win.lift()
            self.activity_win.focus_force()
            return
        win = tk.Toplevel(self.root)
        win.title("成员活跃度(离线追踪)")
        win.geometry("1000x560")
        win.minsize(860, 440)
        self.activity_win = win

        note = ("说明: 官方API没有“最后在线时间”,这里根据成员数据变化(捐兵/收兵/等级/战争进攻次数)近似判断活跃度。\n"
                "程序每次查询会自动记录快照(自动刷新时每5分钟最多一次);需要程序持续运行或定期打开才能积累历史。\n"
                "无变化 ≥7天=关注, ≥14天=警告, ≥30天=严重;白名单成员不会被标记。")
        ttk.Label(win, text=note, foreground="#666666",
                  wraplength=960, justify="left").pack(anchor="w", padx=12, pady=(10, 2))

        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=12, pady=(4, 6))
        ttk.Button(bar, text="刷新快照", command=self.refresh_activity).pack(side="left", padx=3)
        ttk.Button(bar, text="加入白名单", command=lambda: self.toggle_whitelist(True)).pack(side="left", padx=3)
        ttk.Button(bar, text="移出白名单", command=lambda: self.toggle_whitelist(False)).pack(side="left", padx=3)
        ttk.Button(bar, text="导出待处理名单", command=self.export_activity_csv).pack(side="left", padx=3)
        ttk.Button(bar, text="关闭", command=win.destroy).pack(side="right", padx=3)

        frame = ttk.Frame(win)
        frame.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        cols = ("name", "role", "th", "trophies", "donations", "last", "days", "status", "white")
        heads = {"name": "成员", "role": "职位", "th": "大本", "trophies": "奖杯",
                 "donations": "捐兵", "last": "上次变化", "days": "无变化天数",
                 "status": "状态", "white": "白名单"}
        widths = {"name": 160, "role": 70, "th": 55, "trophies": 70, "donations": 70,
                  "last": 130, "days": 90, "status": 110, "white": 60}
        self.act_table = ttk.Treeview(frame, columns=cols, show="headings")
        for c in cols:
            self.act_table.heading(c, text=heads[c])
            self.act_table.column(c, width=widths[c], anchor="center")
        self.act_table.column("name", anchor="w")
        ys = ttk.Scrollbar(frame, orient="vertical", command=self.act_table.yview)
        self.act_table.configure(yscrollcommand=ys.set)
        self.act_table.pack(side="left", fill="both", expand=True)
        ys.pack(side="right", fill="y")
        for style, bg in (("warn", "#fdeecb"), ("alert", "#f8d3d3"),
                          ("severe", "#e8a8a8"), ("white", "#eeeeee")):
            self.act_table.tag_configure(style, background=bg)

        self.render_activity()

    def activity_status(self, tag, days, whitelist):
        if tag in whitelist:
            return "白名单", "white"
        if days >= ACTIVITY_SEVERE_DAYS:
            return "严重(≥30天)", "severe"
        if days >= ACTIVITY_ALERT_DAYS:
            return "警告(≥14天)", "alert"
        if days >= ACTIVITY_WARN_DAYS:
            return "关注(≥7天)", "warn"
        return "正常", ""

    def render_activity(self):
        if self.activity_win is None or not self.activity_win.winfo_exists():
            return
        for iid in self.act_table.get_children():
            self.act_table.delete(iid)
        act = self.activity_data or {}
        wl = set(act.get("whitelist") or [])
        now = time.time()
        rows = []
        for tag, rec in (act.get("members") or {}).items():
            days = max(0.0, (now - float(rec.get("last_change") or now)) / 86400.0)
            status, style = self.activity_status(tag, days, wl)
            rows.append((days, tag, rec, status, style))
        rows.sort(key=lambda r: r[0], reverse=True)
        for days, tag, rec, status, style in rows:
            self.act_table.insert("", "end", iid=tag, tags=(style,) if style else (), values=(
                rec.get("name") or "?",
                ROLE_CN.get(rec.get("role"), rec.get("role") or "-"),
                rec.get("th") or "-",
                rec.get("trophies") or 0,
                rec.get("donations") or 0,
                fmt_ts_local(rec.get("last_change")) if rec.get("last_change") else "-",
                "%.1f" % days,
                status,
                "是" if tag in wl else "",
            ))

    def refresh_activity(self):
        tag = clean_tag(self.tag_entry.get()) or self.clan_tag
        token = self.token_entry.get().strip()
        if not tag or not token:
            messagebox.showwarning("提示", "请先在主窗口填写 API令牌 与 部落标签。")
            return

        def work():
            try:
                ms = api_get("/clans/%s/members?limit=50" % url_tag(tag), token)
            except Exception as e:
                msg = "获取成员列表失败:\n" + api_error_message(e)
                self.post(lambda m=msg: self.show_error(m))
                return
            act = load_activity()
            update_snapshots(ms.get("items") or [], act, now=time.time())
            save_activity(act)
            self._last_snapshot_ts = time.time()
            self.post(lambda a=act: self.after_activity_refresh(a))

        self.run_async(work)

    def after_activity_refresh(self, act):
        self.activity_data = act
        self.render_activity()
        self.set_status("活跃度快照已更新")

    def toggle_whitelist(self, add):
        if self.activity_win is None or not self.activity_win.winfo_exists():
            return
        sel = self.act_table.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在列表中选中成员(可多选)。")
            return
        act = load_activity()
        wl = set(act.get("whitelist") or [])
        if add:
            wl.update(sel)
        else:
            for t in sel:
                wl.discard(t)
        act["whitelist"] = sorted(wl)
        save_activity(act)
        self.activity_data = act
        self.render_activity()

    def export_activity_csv(self):
        act = load_activity()
        members = act.get("members") or {}
        if not members:
            messagebox.showinfo("提示", "还没有活跃度快照,请先查询部落战或点“刷新快照”。")
            return
        wl = set(act.get("whitelist") or [])
        now = time.time()
        todo = []
        for tag, rec in members.items():
            days = max(0.0, (now - float(rec.get("last_change") or now)) / 86400.0)
            status, _ = self.activity_status(tag, days, wl)
            if status not in ("白名单", "正常"):
                todo.append((tag, rec, days, status))
        todo.sort(key=lambda r: r[2], reverse=True)
        if not todo:
            messagebox.showinfo("提示", "目前没有达到7天无变化的成员。")
            return
        default = "coc_inactive_%s.csv" % time.strftime("%Y%m%d_%H%M")
        path = filedialog.asksaveasfilename(title="导出待处理名单", defaultextension=".csv",
                                            initialfile=default, filetypes=[("CSV文件", "*.csv")])
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                wr = csv.writer(f)
                wr.writerow(["成员", "标签", "职位", "大本", "奖杯", "捐兵",
                             "上次变化", "无变化天数", "状态"])
                for tag, rec, days, status in todo:
                    wr.writerow([rec.get("name") or "?", "#" + tag,
                                 ROLE_CN.get(rec.get("role"), rec.get("role") or "-"),
                                 rec.get("th") or "", rec.get("trophies") or "",
                                 rec.get("donations") or "",
                                 fmt_ts_local(rec.get("last_change")) if rec.get("last_change") else "",
                                 "%.1f" % days, status])
            messagebox.showinfo("成功", "已导出 %d 名待处理成员:\n%s" % (len(todo), path))
        except Exception as e:
            messagebox.showerror("错误", "导出失败: %s" % e)

    # ------------------------------------------------ 部落都城(突袭周末)

    def query_capital(self, silent=False):
        tag, token = self.check_inputs()
        if not tag:
            return
        self.clan_tag = tag
        self.last_mode = "capital"
        self.save_inputs()

        def work():
            try:
                data = api_get("/clans/%s/capitalraidseasons" % url_tag(tag), token)
            except Exception as e:
                msg = "获取部落都城数据失败:\n" + api_error_message(e)
                if silent:
                    self.post(lambda m=msg: self.silent_error(m))
                else:
                    self.post(lambda m=msg: self.show_error(m))
                return
            items = data.get("items") or []
            if items:
                try:
                    update_capital_history(items[0])
                except Exception:
                    pass
            self.post(lambda: self.show_capital(items))

        self.run_async(work)

    def show_capital(self, items):
        if not items:
            messagebox.showinfo("提示", "该部落暂无都城突袭记录。")
            return
        if self.capital_win is not None and self.capital_win.winfo_exists():
            self.capital_win.destroy()
        win = tk.Toplevel(self.root)
        win.title("部落都城(突袭周末)")
        win.geometry("1000x580")
        win.minsize(780, 440)
        self.capital_win = win
        self.capital_seasons = items

        note = ("说明: 官方API只对“最新一次(进行中)突袭”返回成员明细,历史赛季只有团队汇总。\n"
                "颜色规则: 两周都打满=绿色, 有一周没打满=黄色, 两周都没打满=红色。\n"
                "“上次进攻”来自本地记录(每次突袭期间运行程序时自动保存, 需上次突袭期间打开过本程序)。")
        ttk.Label(win, text=note, foreground="#666666", wraplength=960,
                  justify="left").pack(anchor="w", padx=12, pady=(10, 2))

        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=12, pady=(2, 4))
        ttk.Label(bar, text="赛季:").pack(side="left")
        labels = []
        for s in items:
            st = CAPITAL_STATE_CN.get(s.get("state"), s.get("state") or "-")
            labels.append("%s ~ %s (%s)" % (fmt_cn_time(s.get("startTime")),
                                            fmt_cn_time(s.get("endTime")), st))
        self.capital_sel = ttk.Combobox(bar, values=labels, state="readonly", width=36)
        self.capital_sel.pack(side="left", padx=(4, 10))
        self.capital_sel.bind("<<ComboboxSelected>>", self.on_capital_select)
        ttk.Button(bar, text="导出CSV", command=self.export_capital_csv).pack(side="left", padx=3)
        ttk.Button(bar, text="关闭", command=win.destroy).pack(side="right", padx=3)

        self.capital_summary = ttk.Label(win, text="", foreground="#0a58a0")
        self.capital_summary.pack(anchor="w", padx=12, pady=(0, 2))
        self.capital_hint = ttk.Label(win, text="", foreground="#b00020")
        self.capital_hint.pack(anchor="w", padx=12, pady=(0, 4))

        frame = ttk.Frame(win)
        frame.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        cols = ("name", "attacks", "limit", "pct", "prev", "two", "loot", "status")
        heads = {"name": "成员", "attacks": "本次进攻", "limit": "攻击上限",
                 "pct": "使用率", "prev": "上次进攻", "two": "两周情况",
                 "loot": "首都资源", "status": "状态"}
        widths = {"name": 170, "attacks": 85, "limit": 85, "pct": 75,
                  "prev": 85, "two": 85, "loot": 110, "status": 85}
        self.capital_table = ttk.Treeview(frame, columns=cols, show="headings")
        for c in cols:
            self.capital_table.heading(c, text=heads[c])
            self.capital_table.column(c, width=widths[c], anchor="center")
        self.capital_table.column("name", anchor="w")
        ys = ttk.Scrollbar(frame, orient="vertical", command=self.capital_table.yview)
        self.capital_table.configure(yscrollcommand=ys.set)
        self.capital_table.pack(side="left", fill="both", expand=True)
        ys.pack(side="right", fill="y")
        for style, bg in (("full", "#d6f2d6"), ("part", "#fdeecb"), ("zero", "#f8d3d3")):
            self.capital_table.tag_configure(style, background=bg)

        self.capital_sel.current(0)
        self.render_capital(0)

    def on_capital_select(self, event=None):
        if self.capital_sel is None:
            return
        idx = self.capital_sel.current()
        if idx >= 0:
            self.render_capital(idx)

    def capital_rows(self, season):
        """计算某赛季成员的展示行(含上次刀数与两周评价)"""
        members = season.get("members") or []
        hist = load_capital_history()
        cur_key = str(season.get("startTime") or "")
        prev_keys = [k for k in (hist.get("seasons") or {}) if k < cur_key]
        prev_members = ((hist["seasons"][max(prev_keys)] if prev_keys else {}) or {}).get("members") or {}
        rows = []
        for m in members:
            a = int(m.get("attacks") or 0)
            lim = int(m.get("attackLimit") or 0) + int(m.get("bonusAttackLimit") or 0)
            cur_full = bool(lim) and a >= lim
            pm = prev_members.get(clean_tag(m.get("tag", "")))
            if pm:
                p_att = int(pm.get("attacks") or 0)
                p_lim = int(pm.get("limit") or 0)
                p_full = bool(p_lim) and p_att >= p_lim
                prev_text = str(p_att)
                two = "%s/%s" % ("满" if p_full else "未", "满" if cur_full else "未")
                if p_full and cur_full:
                    style = "full"
                elif p_full or cur_full:
                    style = "part"
                else:
                    style = "zero"
            else:
                prev_text = "-"
                two = "无/满" if cur_full else "无/未"
                style = "full" if cur_full else "part"
            if a <= 0:
                status = "未进攻"
            elif cur_full:
                status = "打满"
            else:
                status = "未打满"
            rows.append({
                "name": m.get("name") or "?",
                "tag": clean_tag(m.get("tag", "")),
                "attacks": a,
                "limit": lim,
                "pct": ("%.0f%%" % (a * 100.0 / lim)) if lim else "-",
                "prev": prev_text,
                "two": two,
                "loot": m.get("capitalResourcesLooted") or 0,
                "status": status,
                "style": style,
            })
        rows.sort(key=lambda r: r["attacks"], reverse=True)
        return rows, bool(prev_members)

    def render_capital(self, idx):
        if not self.capital_seasons or idx < 0 or idx >= len(self.capital_seasons):
            return
        if self.capital_table is None or not self.capital_table.winfo_exists():
            return
        for iid in self.capital_table.get_children():
            self.capital_table.delete(iid)
        s = self.capital_seasons[idx]
        members = s.get("members") or []
        st = CAPITAL_STATE_CN.get(s.get("state"), s.get("state") or "-")

        def num(v, default="-"):
            return v if v is not None else default

        summary = ("%s | 完成突袭 %s 次 | 团队资源 %s | 摧毁区域 %s | 成员 %d 人" % (
            st, num(s.get("raidsCompleted")), num(s.get("capitalTotalLoot")),
            num(s.get("enemyDistrictsDestroyed")), len(members)))
        if members:
            total_atk = sum(int(m.get("attacks") or 0) for m in members)
            total_limit = sum(int(m.get("attackLimit") or 0) + int(m.get("bonusAttackLimit") or 0)
                              for m in members)
            summary += " | 全员进攻 %d/%d 次" % (total_atk, total_limit)
        self.capital_summary.config(text=summary)

        if not members:
            self.capital_hint.config(text="该赛季暂无成员明细(官方API只提供最新一次突袭的成员数据)。")
            return

        rows, has_prev = self.capital_rows(s)
        if has_prev:
            self.capital_hint.config(text="")
        else:
            self.capital_hint.config(
                text="未找到上一次突袭的本地记录(首次使用或上次突袭期间未运行程序),本次颜色按本周表现判断;"
                     "下次突袭起将按两周情况判断。")

        for r in rows:
            iid = r.get("tag")
            kwargs = {"tags": (r["style"],)}
            if iid:
                kwargs["iid"] = iid
            self.capital_table.insert("", "end", values=(
                r["name"], r["attacks"], r["limit"] or "-", r["pct"],
                r["prev"], r["two"], r["loot"], r["status"],
            ), **kwargs)

    def export_capital_csv(self):
        if not self.capital_seasons:
            messagebox.showinfo("提示", "还没有都城数据,请先点击“部落都城”。")
            return
        idx = self.capital_sel.current() if self.capital_sel is not None else 0
        if idx < 0:
            idx = 0
        s = self.capital_seasons[idx]
        members = s.get("members") or []
        if not members:
            messagebox.showinfo("提示", "当前选中的赛季没有成员明细,无法导出。")
            return
        rows, _ = self.capital_rows(s)
        default = "coc_capital_%s.csv" % time.strftime("%Y%m%d_%H%M")
        path = filedialog.asksaveasfilename(title="导出都城成员数据", defaultextension=".csv",
                                            initialfile=default, filetypes=[("CSV文件", "*.csv")])
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                wr = csv.writer(f)
                wr.writerow(["成员", "标签", "本次进攻", "攻击上限", "使用率",
                             "上次进攻", "两周情况", "首都资源", "状态"])
                for r in rows:
                    wr.writerow([r["name"], ("#" + r["tag"]) if r["tag"] else "",
                                 r["attacks"], r["limit"] or "", r["pct"],
                                 r["prev"], r["two"], r["loot"], r["status"]])
            messagebox.showinfo("成功", "已导出:\n%s" % path)
        except Exception as e:
            messagebox.showerror("错误", "导出失败: %s" % e)

    def show_empty(self, msg=""):
        self.wars = []
        self.round_wars = []
        self.sel.config(values=[], state="disabled")
        self.update_sides()
        self.render()
        if msg:
            self.info_label.config(text=msg, foreground="#c26a00")

    def update_sides(self):
        if not self.wars:
            self.rb_me.config(text="我方", state="disabled", value="")
            self.rb_opp.config(text="敌方", state="disabled", value="")
            return
        me, other = self.oriented_sides(self.wars[0])
        me_tag = clean_tag(me.get("tag", ""))
        other_tag = clean_tag(other.get("tag", ""))
        self.rb_me.config(text="我方: %s" % (me.get("name") or "?"), state="normal", value=me_tag)
        if self.agg_mode:
            self.rb_opp.config(text="敌方(汇总不可用)", state="disabled", value=other_tag)
        else:
            self.rb_opp.config(text="敌方: %s" % (other.get("name") or "?"), state="normal", value=other_tag)
        if self.side_var.get() not in (me_tag, other_tag):
            self.side_var.set(me_tag)

    def render(self):
        self.table.delete(*self.table.get_children())
        self.rows = []
        self.tag_name = {}
        if not self.wars:
            self.info_label.config(text="")
            return
        w0 = self.wars[0]
        me, other = self.oriented_sides(w0)
        me_tag = clean_tag(me.get("tag", ""))
        side_tag = self.side_var.get() or me_tag

        for w in self.wars:
            for side in (w.get("clan"), w.get("opponent")):
                for m in (side or {}).get("members") or []:
                    t = clean_tag(m.get("tag", ""))
                    if t:
                        self.tag_name[t] = m.get("name", "?")

        agg, apm_sum = collect_side(self.wars, side_tag)
        rows = make_rows(agg, apm_sum)
        for i, r in enumerate(rows):
            best_s = ("%d★ (%d%%)" % (r["best_stars"], r["best_dest"])) if r["best_stars"] is not None else "-"
            avg_s = ("%.2f" % r["avg"]) if r["n"] else "-"
            vals = (r["pos"], r["name"], r["th"], r["n"], r["stars"], r["dest"],
                    avg_s, best_s, r["def_stars"], r["def_dest"], r["exp"], r["missed"])
            if r["n"] == 0:
                tag = "none"
            elif r["best_stars"] == 3:
                tag = "green"
            elif r["best_stars"] >= 1:
                tag = "orange"
            else:
                tag = "red"
            self.table.insert("", "end", iid=str(i), values=vals, tags=(tag,))
            self.rows.append(r)
        self.update_info()

    def update_info(self):
        w0 = self.wars[0]
        state = STATE_CN.get(w0.get("state"), w0.get("state") or "-")
        if self.agg_mode:
            stars = sum(int((self.oriented_sides(w)[0]).get("stars") or 0) for w in self.wars)
            dest = sum(int((self.oriented_sides(w)[0]).get("destructionPercentage") or 0) for w in self.wars)
            self.info_label.config(text="CWL联赛汇总: 共%d轮 | 我方合计 %d★ | 合计摧毁率 %d%% | 赛季 %s"
                                  % (len(self.wars), stars, dest, self.cwl_season),
                                  foreground="#0a58a0")
        else:
            me, other = self.oriented_sides(w0)
            team = w0.get("teamSize")
            self.info_label.config(
                text="我方 %s %d★ %d%%  VS  敌方 %s %d★ %d%%   |   %dv%d   |   %s   |   开战 %s"
                % (me.get("name"), me.get("stars") or 0, me.get("destructionPercentage") or 0,
                   other.get("name"), other.get("stars") or 0, other.get("destructionPercentage") or 0,
                   team, team, state, fmt_cn_time(w0.get("startTime"))),
                foreground="#0a58a0")

    def on_select(self, event=None):
        key = self.sel_map.get(self.sel.get())
        if key is None:
            return
        if key == "agg":
            self.wars = self.round_wars
            self.agg_mode = True
            self.side_var.set(self.clan_tag)
        else:
            self.wars = [self.round_wars[key]]
            self.agg_mode = False
        self.update_sides()
        self.render()

    def on_side_change(self):
        self.render()

    # ------------------------------------------------ 明细 / 导出 / 帮助

    def on_double(self, event):
        sel = self.table.selection()
        if not sel:
            return
        try:
            idx = int(sel[0])
        except ValueError:
            return
        if idx < 0 or idx >= len(self.rows):
            return
        r = self.rows[idx]
        win = tk.Toplevel(self.root)
        win.title("战斗明细 - %s (大本%d)" % (r["name"], r["th"]))
        win.geometry("800x430")
        frame = tk.Frame(win)
        frame.pack(fill="both", expand=True, padx=8, pady=8)
        self.detail_box(frame, "进攻明细", r["attacks"], "defenderTag", "进攻对象")
        self.detail_box(frame, "防守明细", r["defs"], "attackerTag", "进攻者")

    def detail_box(self, parent, title, items, key, who_title):
        box = tk.LabelFrame(parent, text=title, padx=4, pady=4)
        box.pack(side="left", fill="both", expand=True, padx=6)
        tv = ttk.Treeview(box, columns=("who", "stars", "dest", "dur"), show="headings", height=16)
        for c, h in (("who", who_title), ("stars", "星数"), ("dest", "摧毁率"), ("dur", "用时")):
            tv.heading(c, text=h)
            tv.column(c, width=92, anchor="center")
        for a in items:
            who_tag = clean_tag(a.get(key, ""))
            tv.insert("", "end", values=(
                self.tag_name.get(who_tag, "?"),
                "%d★" % int(a.get("stars") or 0),
                "%d%%" % int(a.get("destructionPercentage") or 0),
                fmt_dur(a.get("duration")),
            ))
        ys = ttk.Scrollbar(box, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=ys.set)
        ys.pack(side="right", fill="y")
        tv.pack(side="left", fill="both", expand=True)

    def export_csv(self):
        if not self.rows:
            messagebox.showinfo("提示", "当前没有可导出的数据,请先查询。")
            return
        default = "coc_war_%s.csv" % time.strftime("%Y%m%d_%H%M%S")
        path = filedialog.asksaveasfilename(title="导出CSV", defaultextension=".csv",
                                            initialfile=default, filetypes=[("CSV文件", "*.csv")])
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                wr = csv.writer(f)
                wr.writerow(["位置", "成员", "大本", "进攻次数", "总星数", "总摧毁%", "场均星",
                             "最佳进攻星", "最佳进攻摧毁%", "被攻星数", "被摧毁%", "应打次数", "未进攻次数"])
                for r in self.rows:
                    wr.writerow([r["pos"], r["name"], r["th"], r["n"], r["stars"], r["dest"],
                                 ("%.2f" % r["avg"]) if r["n"] else "",
                                 r["best_stars"] if r["best_stars"] is not None else "",
                                 r["best_dest"] if r["best_dest"] is not None else "",
                                 r["def_stars"], r["def_dest"], r["exp"], r["missed"]])
            messagebox.showinfo("成功", "已导出到:\n%s" % path)
        except Exception as e:
            messagebox.showerror("错误", "导出失败: %s" % e)

    def show_help(self):
        messagebox.showinfo("帮助",
            "使用步骤:\n\n"
            "1. 获取API令牌: 用浏览器打开 developer.clashofclans.com,\n"
            "   登录(谷歌账号等均可)后点击 \"Create Key\";\n"
            "   - 名称随意填写;\n"
            "   - IP地址填写你当前电脑的公网IP(必填,创建时实时校验);\n"
            "   - 勾选 Clash of Clans,创建后复制令牌;\n\n"
            "2. 把令牌粘贴到\"API令牌\"框,部落标签填入\"部落标签\"框(如 #2LJQ2YVY);\n\n"
            "3. 点击\"查询当前部落战\"查看每位成员的进攻/防守数据:\n"
            "   - 绿色行 = 打出过3星, 橙色 = 1~2星, 红色 = 只打出0星, 灰色 = 还未进攻;\n"
            "   - 双击某一行可查看该成员每一次进攻与防守的明细;\n\n"
            "4. 点击\"部落联赛CWL\"可查看联赛每一轮或全部轮次的汇总;\n\n"
            "5. 点击\"部落都城\"查看突袭周末每位成员的进攻次数:\n"
            "   - 攻击上限 = 基础次数 + 奖励次数(通常5+1=6次);\n"
            "   - 颜色: 两周都打满=绿, 一周没满=黄, 两周都没满=红;\n"
            "   - \"上次进攻\"来自本地记录(需上次突袭期间打开过本程序);\n"
            "   - 官方API只提供最新一次突袭的成员明细;\n\n"
            "6. 点击\"活跃度\"查看成员离线追踪:\n"
            "   程序自动记录成员数据变化(捐兵/收兵/等级/战争进攻),\n"
            "   无变化 ≥7天=关注, ≥14天=警告, ≥30天=严重;\n"
            "   可把成员加入白名单豁免, 也可导出待处理名单。\n"
            "   (官方API只读, 无法自动踢人, 请在游戏内操作)\n\n"
            "7. 点击\"导出CSV\"把当前表格保存为Excel可打开的CSV文件。\n\n"
            "8. 当前部落战视图每30秒自动刷新一次;\n"
            "   点\"暂停刷新\"可冻结当前数据,再点\"继续刷新\"恢复。\n\n"
            "注意: 令牌与IP绑定,换网络后需重新创建令牌。")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
