# -*- coding: utf-8 -*-
"""暂停/恢复自动刷新 功能测试(隐藏窗口)"""
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
app.refresh_interval = 800   # 测试用: 0.8 秒刷新一次

app.query_current(silent=True)


def wait_done(timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline and app.busy:
        root.update()
        time.sleep(0.05)
    root.update()


wait_done()
print("[1] 查询完成 rows =", len(app.table.get_children()), "| dialogs =", len(dialogs))

app.toggle_pause()
assert app.paused is True
assert app.pause_btn.cget("text") == "继续刷新"
print("[2] 已暂停, 按钮文字 =", app.pause_btn.cget("text"), "| status =", app.status_var.get())

first = app.table.get_children()[0] if app.table.get_children() else None
time.sleep(2.0)          # 跨过两个自动刷新周期
root.update()
assert not app.busy, "暂停期间不应有刷新请求"
assert app.table.get_children()[0] == first
print("[3] 暂停期间数据未变化 OK")

app.toggle_pause()
assert app.paused is False
assert app.pause_btn.cget("text") == "暂停刷新"
print("[4] 已恢复, 按钮文字 =", app.pause_btn.cget("text"), "| status =", app.status_var.get())

time.sleep(1.5)          # 等一个周期, 应触发一次静默刷新
root.update()
print("[5] 恢复后自动刷新执行中:", app.busy, "| rows =", len(app.table.get_children()))

wait_done(20)
root.destroy()
print("PAUSE TEST PASSED")
