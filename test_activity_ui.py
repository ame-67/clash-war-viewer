# -*- coding: utf-8 -*-
"""活跃度窗口 UI 测试(隐藏窗口, 模拟 API)"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tkinter as tk
import clash_war_viewer as m

tmp = os.path.join(os.environ.get("TEMP", "."), "coc_activity_test")
os.makedirs(tmp, exist_ok=True)
m.data_dir = lambda: tmp

dialogs = []
m.messagebox.showerror = lambda *a, **k: dialogs.append(("error",) + a)
m.messagebox.showinfo = lambda *a, **k: dialogs.append(("info",) + a)
m.messagebox.showwarning = lambda *a, **k: dialogs.append(("warn",) + a)
m.messagebox.askyesno = lambda *a, **k: True

fake_members = {"items": [
    {"tag": "#AAA", "name": "超活跃", "role": "leader", "donations": 500,
     "donationsReceived": 600, "expLevel": 200, "townHallLevel": 16, "trophies": 5000},
    {"tag": "#BBB", "name": "离线8天", "role": "member", "donations": 3,
     "donationsReceived": 2, "expLevel": 120, "townHallLevel": 14, "trophies": 2000},
    {"tag": "#CCC", "name": "离线40天", "role": "admin", "donations": 0,
     "donationsReceived": 0, "expLevel": 90, "townHallLevel": 12, "trophies": 1000},
]}


def fake_api_get(path, token, retries=3):
    if "members" in path:
        return fake_members
    raise RuntimeError("unexpected request: " + path)


m.api_get = fake_api_get

now = time.time()
act = {"members": {
    "AAA": {"name": "超活跃", "role": "leader", "th": 16, "trophies": 5000, "donations": 500,
            "last_change": now,
            "values": {"donations": 500, "donationsReceived": 600, "expLevel": 200, "townHallLevel": 16}},
    "BBB": {"name": "离线8天", "role": "member", "th": 14, "trophies": 2000, "donations": 3,
            "last_change": now - 8 * 86400,
            "values": {"donations": 3, "donationsReceived": 2, "expLevel": 120, "townHallLevel": 14}},
    "CCC": {"name": "离线40天", "role": "admin", "th": 12, "trophies": 1000, "donations": 0,
            "last_change": now - 40 * 86400,
            "values": {"donations": 0, "donationsReceived": 0, "expLevel": 90, "townHallLevel": 12}},
}, "whitelist": []}
m.save_activity(act)

root = tk.Tk()
root.withdraw()
app = m.App(root)
app.activity_data = act
app.open_activity()

kids = app.act_table.get_children()
print("rows:", len(kids))
for iid in kids:
    print("  ", app.act_table.item(iid)["values"])

vals = {iid: app.act_table.item(iid)["values"] for iid in kids}
assert vals["AAA"][7] == "正常", vals["AAA"]
assert vals["BBB"][7] == "关注(≥7天)", vals["BBB"]
assert vals["CCC"][7] == "严重(≥30天)", vals["CCC"]
print("RENDER PASSED")

app.act_table.selection_set("CCC")
app.toggle_whitelist(True)
wl = m.load_activity()["whitelist"]
assert "CCC" in wl, wl
assert app.act_table.item("CCC")["values"][7] == "白名单"
print("WHITELIST ADD PASSED")

app.act_table.selection_set("CCC")
app.toggle_whitelist(False)
assert "CCC" not in m.load_activity()["whitelist"]
print("WHITELIST REMOVE PASSED")

out = os.path.join(tmp, "todo.csv")
m.filedialog.asksaveasfilename = lambda **k: out
app.export_activity_csv()
content = open(out, encoding="utf-8-sig").read()
print("CSV:")
print(content[:300])
assert "离线8天" in content and "离线40天" in content and "超活跃" not in content
print("EXPORT PASSED")

app.refresh_activity()
deadline = time.time() + 10
while time.time() < deadline and app.busy:
    root.update()
    time.sleep(0.05)
root.update()
assert len(app.act_table.get_children()) == 3
assert app.act_table.item("CCC")["values"][7] == "严重(≥30天)"
print("REFRESH PASSED")

root.destroy()
print("ACTIVITY UI TEST PASSED")
