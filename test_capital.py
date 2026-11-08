# -*- coding: utf-8 -*-
"""部落都城测试: 上次刀数 / 两周颜色规则 / 无历史回退"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tkinter as tk
import clash_war_viewer as m

tmp = os.path.join(os.environ.get("TEMP", "."), "coc_capital_test")
os.makedirs(tmp, exist_ok=True)
m.data_dir = lambda: tmp

dialogs = []
m.messagebox.showerror = lambda *a, **k: dialogs.append(("error",) + a)
m.messagebox.showinfo = lambda *a, **k: dialogs.append(("info",) + a)
m.messagebox.showwarning = lambda *a, **k: dialogs.append(("warn",) + a)
m.messagebox.askyesno = lambda *a, **k: True

CUR_START = "20261106T070000.000Z"
PREV_START = "20261030T070000.000Z"

# 上一次突袭的本地历史(由程序在突袭期间自动保存)
m.save_capital_history({"seasons": {PREV_START: {
    "start": PREV_START, "end": "20261102T070000.000Z",
    "members": {
        "A1": {"name": "打满甲", "attacks": 6, "limit": 6},
        "A2": {"name": "打满乙", "attacks": 3, "limit": 6},
        "A3": {"name": "半程丙", "attacks": 5, "limit": 5},
        "A4": {"name": "未打丁", "attacks": 0, "limit": 5},
    },
}}})

seasons = [
    {"state": "ongoing", "startTime": CUR_START, "endTime": "20261109T070000.000Z",
     "raidsCompleted": 2, "capitalTotalLoot": 123456, "enemyDistrictsDestroyed": 12,
     "members": [
         {"tag": "#A1", "name": "打满甲", "attacks": 6, "attackLimit": 5,
          "bonusAttackLimit": 1, "capitalResourcesLooted": 30000},
         {"tag": "#A2", "name": "打满乙", "attacks": 6, "attackLimit": 5,
          "bonusAttackLimit": 1, "capitalResourcesLooted": 25000},
         {"tag": "#A3", "name": "半程丙", "attacks": 5, "attackLimit": 5,
          "bonusAttackLimit": 0, "capitalResourcesLooted": 9000},
         {"tag": "#A4", "name": "未打丁", "attacks": 0, "attackLimit": 5,
          "bonusAttackLimit": 0, "capitalResourcesLooted": 0},
         {"tag": "#A5", "name": "新来戊", "attacks": 6, "attackLimit": 5,
          "bonusAttackLimit": 1, "capitalResourcesLooted": 20000},
         {"tag": "#A6", "name": "新来己", "attacks": 3, "attackLimit": 5,
          "bonusAttackLimit": 0, "capitalResourcesLooted": 5000},
     ]},
    {"state": "ended", "startTime": PREV_START, "endTime": "20261102T070000.000Z",
     "raidsCompleted": 3, "capitalTotalLoot": 99999, "enemyDistrictsDestroyed": 8, "members": []},
]


def fake_api_get(path, token, retries=3):
    if "capitalraidseasons" in path:
        return {"items": seasons}
    raise RuntimeError("unexpected request: " + path)


m.api_get = fake_api_get

root = tk.Tk()
root.withdraw()
app = m.App(root)
app.token_entry.delete(0, "end")
app.token_entry.insert(0, "fake-token-for-test")
app.tag_entry.delete(0, "end")
app.tag_entry.insert(0, "#2LJQ2YVY")

app.query_capital()
deadline = time.time() + 15
while time.time() < deadline and app.busy:
    root.update()
    time.sleep(0.05)
root.update()

assert app.capital_win is not None and app.capital_win.winfo_exists()
rows = app.capital_table.get_children()
assert len(rows) == 6, rows

vals = {iid: list(app.capital_table.item(iid)["values"]) for iid in rows}
tags = {iid: app.capital_table.item(iid)["tags"] for iid in rows}
print("summary:", app.capital_summary.cget("text"))
for iid in ("A1", "A2", "A3", "A4", "A5", "A6"):
    print(iid, vals[iid], tags[iid])

# 两周都打满 -> 绿(full); 上次 6
assert tags["A1"] == ["full"], tags["A1"]
assert str(vals["A1"][4]) == "6" and vals["A1"][5] == "满/满", vals["A1"]
# 上次没满(3), 本次满 -> 黄(part)
assert tags["A2"] == ["part"], tags["A2"]
assert str(vals["A2"][4]) == "3" and vals["A2"][5] == "未/满", vals["A2"]
# 两周都满 -> 绿
assert tags["A3"] == ["full"], tags["A3"]
# 两周都没满 -> 红(zero)
assert tags["A4"] == ["zero"], tags["A4"]
assert vals["A4"][5] == "未/未", vals["A4"]
# 无上次记录: 本次满 -> 绿, 显示 无/满
assert tags["A5"] == ["full"], tags["A5"]
assert str(vals["A5"][4]) == "-" and vals["A5"][5] == "无/满", vals["A5"]
# 无上次记录: 本次未满 -> 黄
assert tags["A6"] == ["part"], tags["A6"]
print("TWO-WEEK COLOR RULE PASSED")

# 有历史记录时不显示提示
assert app.capital_hint.cget("text") == "", app.capital_hint.cget("text")
print("HISTORY HINT CLEARED")

# 导出 CSV 包含 上次进攻 / 两周情况
out = os.path.join(tmp, "capital.csv")
m.filedialog.asksaveasfilename = lambda **k: out
app.export_capital_csv()
content = open(out, encoding="utf-8-sig").read()
print(content[:260])
assert "上次进攻" in content and "两周情况" in content
assert "打满乙,#A2,6,6,100%,3,未/满,25000,打满" in content
print("CSV PASSED")

# 无历史回退: 本次打满 -> 绿, 未满 -> 黄, 并显示提示
m.save_capital_history({"seasons": {}})
app.render_capital(0)
root.update()
tags2 = {iid: app.capital_table.item(iid)["tags"] for iid in app.capital_table.get_children()}
assert tags2["A1"] == ["full"], tags2["A1"]
assert tags2["A2"] == ["full"], tags2["A2"]
assert tags2["A4"] == ["part"], tags2["A4"]
assert "未找到上一次突袭的本地记录" in app.capital_hint.cget("text")
print("NO-HISTORY FALLBACK PASSED")

root.destroy()
print("CAPITAL TEST PASSED")
