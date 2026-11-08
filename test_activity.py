# -*- coding: utf-8 -*-
"""活跃度追踪离线测试: 快照更新 / 周清零处理 / 战争进攻 / 档位判定"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clash_war_viewer as m


def member(tag, name, don=10, rec=10, lvl=100, th=15):
    return {"tag": "#" + tag, "name": name, "role": "member", "donations": don,
            "donationsReceived": rec, "expLevel": lvl, "townHallLevel": th,
            "trophies": 3000}


war = {
    "state": "inWar",
    "preparationStartTime": "20261027T000000.000Z",
    "clan": {"tag": "#TEST", "members": [
        {"tag": "#A", "attacks": [{"stars": 3}, {"stars": 2}]},
        {"tag": "#B", "attacks": []},
    ]},
    "opponent": {"tag": "#OPP", "members": []},
}

act = {"members": {}, "whitelist": []}
act = m.update_snapshots([member("A", "甲"), member("B", "乙")], act, now=1000)
assert act["members"]["A"]["last_change"] == 1000
assert act["members"]["B"]["last_change"] == 1000

act = m.update_snapshots([member("A", "甲", don=12), member("B", "乙", don=3)], act, now=2000)
assert act["members"]["A"]["last_change"] == 2000, act["members"]["A"]
assert act["members"]["B"]["last_change"] == 1000, act["members"]["B"]

act = m.update_snapshots([member("A", "甲", don=12), member("B", "乙", don=3)],
                         act, war=war, now=3000, side_tag="TEST")
assert act["members"]["A"]["last_change"] == 2000, act["members"]["A"]
assert act["members"]["A"]["war"] == {"key": "20261027T000000.000Z", "count": 2}

war2 = {"state": "inWar", "preparationStartTime": "20261027T000000.000Z",
        "clan": {"tag": "#TEST", "members": [
            {"tag": "#A", "attacks": [{"stars": 3}, {"stars": 2}, {"stars": 1}]},
            {"tag": "#B", "attacks": []}]},
        "opponent": {"tag": "#OPP", "members": []}}
act = m.update_snapshots([member("A", "甲", don=12), member("B", "乙", don=3)],
                         act, war=war2, now=4000, side_tag="TEST")
assert act["members"]["A"]["last_change"] == 4000, act["members"]["A"]
assert act["members"]["B"]["last_change"] == 1000

war_swap = {"state": "inWar", "preparationStartTime": "20261027T000000.000Z",
            "clan": {"tag": "#OPP", "members": []},
            "opponent": {"tag": "#TEST", "members": [
                {"tag": "#A", "attacks": [{"stars": 3}, {"stars": 2}, {"stars": 1}, {"stars": 0}]}]}}
act = m.update_snapshots([member("A", "甲", don=12)], act, war=war_swap, now=4500, side_tag="TEST")
assert act["members"]["A"]["last_change"] == 4500, act["members"]["A"]

act = m.update_snapshots([member("A", "甲", don=12), member("C", "丙")], act, now=5000)
assert set(act["members"]) == {"A", "C"}, act["members"]
assert act["members"]["C"]["last_change"] == 5000
print("SNAPSHOT LOGIC PASSED")

cases = [(0.5, "正常"), (6.9, "正常"), (7.0, "关注(≥7天)"), (13.9, "关注(≥7天)"),
         (14.0, "警告(≥14天)"), (29.9, "警告(≥14天)"), (30.0, "严重(≥30天)"), (60, "严重(≥30天)")]
for days, expect in cases:
    status, _ = m.App.activity_status(None, "#X", days, set())
    assert status == expect, (days, status, expect)
status, style = m.App.activity_status(None, "#X", 60, {"#X"})
assert status == "白名单" and style == "white", (status, style)
print("THRESHOLD LOGIC PASSED")
