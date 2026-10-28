# -*- coding: utf-8 -*-
"""端到端冒烟测试: 用真实 API 数据跑一遍 UI 渲染路径(隐藏窗口)"""
import os, sys, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tkinter as tk
import clash_war_viewer as m

CFG = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "CoCWarViewer", "config.json")
cfg = json.load(open(CFG, encoding="utf-8"))

dialogs = []
m.messagebox.showerror = lambda *a, **k: dialogs.append(("error",) + a)
m.messagebox.showinfo = lambda *a, **k: dialogs.append(("info",) + a)
m.messagebox.showwarning = lambda *a, **k: dialogs.append(("warn",) + a)
m.messagebox.askyesno = lambda *a, **k: True

root = tk.Tk()
root.withdraw()
app = m.App(root)
app.token_entry.delete(0, "end")
app.token_entry.insert(0, cfg["token"])
app.tag_entry.delete(0, "end")
app.tag_entry.insert(0, cfg["clan_tag"])

# --- 测试1: 查询当前部落战 ---
app.query_current()
deadline = time.time() + 40
while time.time() < deadline and app.busy:
    root.update()
    time.sleep(0.05)
root.update()
rows = app.table.get_children()
print("[current] rows:", len(rows), "| status:", app.status_var.get(), "| dialogs:", len(dialogs))
print("[current] info:", app.info_label.cget("text"))
for iid in rows[:6]:
    print("   ", app.table.item(iid)["values"])

# --- 测试2: 联赛查询(应给出友好提示而不是静默/抛错) ---
dialogs.clear()
app.query_cwl()
deadline = time.time() + 40
while time.time() < deadline and app.busy:
    root.update()
    time.sleep(0.05)
root.update()
print("[cwl] status:", app.status_var.get(), "| dialogs:", dialogs[:2], "| info:", app.info_label.cget("text"))

# --- 测试3: 双击明细(直接调用,验证不抛异常) ---
kids = app.table.get_children()
if kids:
    app.table.selection_set(kids[0])
    try:
        app.on_double(None)
        print("[detail] ok, toplevels:", len(root.winfo_children()))
    except Exception as e:
        print("[detail] EXCEPTION:", repr(e))

# --- 测试4: 战争日志(应弹出"部落战争日志"窗口并列出记录) ---
dialogs.clear()
app.query_warlog()
deadline = time.time() + 40
while time.time() < deadline and app.busy:
    root.update()
    time.sleep(0.05)
root.update()
tops = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
warlog_win = None
for w in tops:
    if w.title() == "部落战争日志":
        warlog_win = w
print("[warlog] toplevels:", len(tops), "| dialogs:", dialogs)
if warlog_win is not None:
    trees = [k for k in warlog_win.winfo_children()
             if k.winfo_class() == "TFrame"]
    print("[warlog] 窗口已打开, 行数:", end=" ")
    n = 0
    for k in warlog_win.winfo_children():
        if k.winfo_class() == "TFrame":
            for sub in k.winfo_children():
                if sub.winfo_class() == "Treeview":
                    n = len(sub.get_children())
                    for iid in sub.get_children()[:3]:
                        print("\n     ", sub.item(iid)["values"], end="")
    print(n)
else:
    print("[warlog] 失败: 未打开战争日志窗口")

root.destroy()
print("SMOKE TEST DONE")
