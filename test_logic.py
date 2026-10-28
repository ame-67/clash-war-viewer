# -*- coding: utf-8 -*-
"""离线逻辑自测: 用假战争数据验证统计计算(结构与真实官方API一致)

真实 API 的成员字段: attacks=[{attackerTag,defenderTag,stars,destructionPercentage,duration}],
opponentAttacks=整数(被攻次数), 因此防守明细需按 defenderTag 反查。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clash_war_viewer as m


def atk(attacker, defender, stars, dest, duration=95):
    return {"attackerTag": "#" + attacker, "defenderTag": "#" + defender,
            "stars": stars, "destructionPercentage": dest, "order": 1, "duration": duration}


def member(tag, name, th, pos, attacks, opp_count):
    return {"tag": "#" + tag, "name": name, "townhallLevel": th, "mapPosition": pos,
            "attacks": attacks, "opponentAttacks": opp_count}


war = {
    "state": "inWar", "teamSize": 3, "attacksPerMember": 2,
    "startTime": "20261025T080000.000Z",
    "clan": {
        "tag": "#TESTCLAN", "name": "测试部落", "stars": 5, "destructionPercentage": 88,
        "members": [
            member("M1", "首领", 16, 1, [atk("M1", "E2", 3, 100), atk("M1", "E1", 2, 75)], 1),
            member("M2", "副首", 15, 2, [atk("M2", "E1", 0, 42)], 1),
            member("M3", "成员甲", 14, 3, [], 0),
        ],
    },
    "opponent": {
        "tag": "#OPPONENT", "name": "敌方部落", "stars": 3, "destructionPercentage": 61,
        "members": [
            member("E1", "敌1", 15, 1, [atk("E1", "M1", 1, 55)], 0),
            member("E2", "敌2", 14, 2, [atk("E2", "M2", 2, 70)], 0),
            member("E3", "敌3", 13, 3, [], 0),
        ],
    },
}

agg, apm = m.collect_side([war], "TESTCLAN")
rows = m.make_rows(agg, apm)
assert apm == 2, apm

r1 = next(r for r in rows if r["name"] == "首领")
assert r1["n"] == 2 and r1["stars"] == 5 and r1["dest"] == 175, r1
assert r1["best_stars"] == 3 and r1["best_dest"] == 100, r1
assert r1["def_stars"] == 1 and r1["def_dest"] == 55, r1
assert r1["missed"] == 0, r1
assert len(r1["defs"]) == 1 and r1["defs"][0]["attackerTag"] == "#E1"

r2 = next(r for r in rows if r["name"] == "副首")
assert r2["n"] == 1 and r2["stars"] == 0 and r2["best_stars"] == 0, r2
assert r2["def_stars"] == 2 and r2["def_dest"] == 70, r2
assert r2["missed"] == 1, r2

r3 = next(r for r in rows if r["name"] == "成员甲")
assert r3["n"] == 0 and r3["missed"] == 2 and r3["defs"] == [], r3

# 敌方视角: 敌1 打出 1 星; 且敌1 被 M1 打了 2 星(防守反查)
agg2, apm2 = m.collect_side([war], "OPPONENT")
rows2 = m.make_rows(agg2, apm2)
r2b = next(r for r in rows2 if r["name"] == "敌1")
assert r2b["stars"] == 1, r2b
# 敌1 被 M1(2星75%) 和 M2(0星42%) 各打一次
assert len(r2b["defs"]) == 2, r2b
assert r2b["def_stars"] == 2 and r2b["def_dest"] == 117, r2b

# 多轮汇总(模拟 CWL 两轮,同一部落)
war2 = {
    "state": "inWar", "teamSize": 3, "attacksPerMember": 1,
    "clan": {"tag": "#TESTCLAN", "name": "测试部落", "stars": 2, "destructionPercentage": 60,
             "members": [member("M1", "首领", 16, 1, [atk("M1", "E9", 2, 60)], 0),
                         member("M2", "副首", 15, 2, [atk("M2", "E9", 1, 40)], 0),
                         member("M3", "成员甲", 14, 3, [], 1)]},
    "opponent": {"tag": "#ENEMY2", "name": "敌2", "stars": 1, "destructionPercentage": 30,
                 "members": [member("E9", "敌9", 14, 1, [atk("E9", "M3", 1, 30)], 0)]},
}
agg3, apm3 = m.collect_side([war, war2], "TESTCLAN")
rows3 = m.make_rows(agg3, apm3)
assert apm3 == 3, apm3
r1b = next(r for r in rows3 if r["name"] == "首领")
assert r1b["n"] == 3 and r1b["stars"] == 7 and r1b["dest"] == 235, r1b
r3b = next(r for r in rows3 if r["name"] == "成员甲")
assert r3b["missed"] == 3 and r3b["def_stars"] == 1 and r3b["def_dest"] == 30, r3b

print("ALL LOGIC TESTS PASSED")
print("首领: 进攻%d次 %d星 %d%% 最佳%d星(%d%%) 被攻%d星 %d%%" % (
    r1b["n"], r1b["stars"], r1b["dest"], r1b["best_stars"], r1b["best_dest"],
    r1b["def_stars"], r1b["def_dest"]))
print("成员甲(汇总): 未进攻%d次, 被攻%d星" % (r3b["missed"], r3b["def_stars"]))
