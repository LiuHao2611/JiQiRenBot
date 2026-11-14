# -*- coding: utf-8 -*-
"""斗破门派系统数据层验收（零依赖、exit-code 可验证）。

运行：
    python src/plugins/doupo/test_factions.py     # 自带 runner
    pytest src/plugins/doupo/test_factions.py

用 importlib 按文件路径直接加载 factions.py，**不触发 doupo/__init__.py**，
以此证明它是零副作用的纯数据模块（不需要 nonebot、不需要 PIL）。
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

PLUGINS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(os.path.dirname(PLUGINS_DIR))
for _p in (REPO_ROOT, PLUGINS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_FP = Path(__file__).with_name("factions.py")
_spec = importlib.util.spec_from_file_location("doupo_factions_standalone", str(_FP))
F = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(F)

VALID_SOURCES = {"S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "G1",
                "C1", "C2", "C3"}


def test_validate_is_clean():
    problems = F.validate()
    assert not problems, "数据自检失败：%s" % problems


def test_pool_sizes_and_tiers():
    assert len(F.FACTIONS) >= 25, "门派太少"
    for pool, minimum in (("starter", 10), ("advanced", 10), ("hidden", 8)):
        n = len(F.by_pool(pool))
        assert n >= minimum, "%s 池只有 %d 个" % (pool, n)
    for tier in F.TIERS:
        assert F.by_tier(tier), "缺 %s 期门派" % tier


def test_starter_pool_is_newbie_only():
    for fid, f in F.by_pool("starter").items():
        assert f["tier"] == "early", "%s 不该在新手池" % fid
        assert int(f["unlock_lv"]) == 1, "%s 新手不该有等级门槛" % fid
    assert all(int(f["unlock_lv"]) >= 40 for f in F.by_pool("advanced").values())
    assert all(int(f["unlock_lv"]) >= 90 for f in F.by_pool("hidden").values())


def test_every_faction_has_npcs_and_sources():
    for fid, f in F.FACTIONS.items():
        assert f["npcs"], "%s 无代表人物" % fid
        assert f["sources"], "%s 无来源" % fid
        unknown = set(f["sources"]) - VALID_SOURCES
        assert not unknown, "%s 有未知来源编号 %s" % (fid, unknown)
        assert f["base"] and f["name"]


def test_random_faction_is_deterministic_and_pool_scoped():
    first = F.random_faction("starter", rng=lambda: 0.0)
    last = F.random_faction("starter", rng=lambda: 0.999999)
    assert first and last and first != last
    for pool in F.POOLS:
        allowed = set(F.by_pool(pool))
        for i in range(200):
            got = F.random_faction(pool, rng=lambda: (i % 100) / 100.0)
            assert got in allowed, "%s 抽到了池外门派 %s" % (pool, got)
    assert F.random_faction("unknown-pool") is None


def test_starter_kit_is_complete():
    for fid in F.FACTIONS:
        kit = F.starter_kit(fid)
        assert kit["faction"] == fid and kit["faction_name"]
        for k in ("skill", "special", "item", "relic"):
            assert kit[k], "%s starter.%s 为空" % (fid, k)


def test_assign_only_adds_fields():
    p = {"lv": 1, "gold": 10000, "name": "测试"}
    before = dict(p)
    kit = F.assign_faction(p, rng=lambda: 0.0)
    assert kit and p["faction"] in F.FACTIONS
    for k, v in before.items():
        assert p[k] == v, "既有字段 %s 被改动" % k
    added = set(p) - set(before)
    assert added == {"faction", "faction_name", "skill", "special", "item", "relic"}
    assert F.faction_of(p) is F.FACTIONS[p["faction"]]
    assert F.faction_of({}) is None


def test_special_skills_unlock_by_level():
    f = F.FACTIONS["guzu"]
    lows = [s["unlock_lv"] for s in f["special_skills"]]
    assert min(lows) > 1, "古族特殊斗技不该 1 级全开"
    assert F.special_skills_at("guzu", 1) == []
    assert len(F.special_skills_at("guzu", 99)) == len(f["special_skills"])
    assert F.special_skills_at("no-such-faction", 99) == []


def test_key_factions_keep_authoritative_config():
    """防止整理数据时把权威设定改坏：抽查几派的关键斗技/器物/异火。"""
    checks = {
        "fengleige": ("三千雷幻身", "三千雷动"),
        "guzu": ("帝印决", "金帝焚天炎"),
        "danta": ("三千焱炎火", "星域"),
        "xingyunge": ("骨灵冷火", "黑魔鼎"),
        "fenyangu": ("九龙雷罡火", "山熔鼎"),
        "tianmingzong": ("天冥修罗手",),
        "jiuyou": ("黄泉天怒",),
        "yunlanzong": ("天道神雷剑诀", "天刑台"),
        "xiaojia": ("狂狮怒罡", "萧族印信"),
    }
    for fid, needles in checks.items():
        blob = str(F.FACTIONS[fid])
        for n in needles:
            assert n in blob, "%s 丢失关键配置 %s" % (fid, n)


def test_game_original_skills_are_marked():
    """游戏自造的绝学必须显式标注，不能被当原著设定。"""
    blob = str(F.FACTIONS["yunlanzong"]) + str(F.FACTIONS["motie"]) + str(F.FACTIONS["mojia"])
    for word in ("天道神雷剑诀", "寒冰屏障", "灭生门", "游戏原创"):
        assert word in blob, "游戏原创标注丢失：%s" % word


def test_no_protagonist_gear_in_faction_starters():
    """主角个人装备/自创斗技不能混入门派发放物。"""
    banned = ("玄重尺", "佛怒火莲", "焚诀", "异火恒古尺")
    for fid, f in F.FACTIONS.items():
        kit = " ".join(str(v) for v in f["starter"].values())
        for b in banned:
            assert b not in kit, "%s 的 starter 混入主角装备 %s" % (fid, b)


def test_community_sources_are_used():
    """用户要求补全社区/论坛/大佬帖子数据：C1/C2/C3 必须真正进入数据。"""
    blob = str(F.FACTIONS)
    for tag in ("C1", "C2", "C3"):
        assert ("[%s]" % tag) in blob, "社区来源 %s 未进入 factions 数据" % tag
    # 至少 50 处社区标注，证明不是空壳
    assert blob.count("[C") >= 50, "社区标注过少：%d" % blob.count("[C")


def test_community_key_skills_attributed():
    """抽查关键门派斗技来自社区整理（人物/门派归属），而非主角个人配置。"""
    checks = {
        "yunlanzong": ("玄岩盾", "风火木壁", "大悲撕风手"),
        "tianmingzong": ("嗜血化骨手", "大裂风", "天冥掌"),
        "hundian": ("九幽魂手", "碎魂冥掌", "黑色骷髅"),
        "jianan": ("血裂斩", "大裂山", "卸力水镜"),
        "xuezong": ("血裂斩", "雷蝠天翼"),
        "taixugulong": ("屠龙剑", "龙皇钟"),
        "jiuyou": ("黄泉大印", "枯叶大毒掌"),
        "guzu": ("龙蛇步法", "万兽枪法"),
        "fenyangu": ("纯阳绵手", "太乙火罗掌"),
        "fengleige": ("风雷爪", "圣像妖凰钟"),
    }
    for fid, needles in checks.items():
        blob = str(F.FACTIONS[fid])
        for n in needles:
            assert n in blob, "%s 缺少社区归属斗技 %s" % (fid, n)


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------
def _run_all():
    fns = [(k, v) for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    ok = 0
    fail = []
    for name, fn in fns:
        try:
            fn()
            ok += 1
            print("PASS  %s" % name)
        except Exception as e:  # noqa: BLE001
            fail.append((name, e))
            print("FAIL  %s  ->  %s: %s" % (name, type(e).__name__, e))
    print("=" * 70)
    print("FACTIONS_TOTAL=%d PASSED=%d FAILED=%d" % (len(fns), ok, len(fail)))
    return 0 if not fail else 1


if __name__ == "__main__":
    sys.exit(_run_all())
