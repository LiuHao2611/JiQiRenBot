# -*- coding: utf-8 -*-
"""斗破门派系统 · 纯数据层（零副作用，不 import nonebot / 不碰现有玩法）。

用途
----
给「新手入道随机分配宗门」提供数据底座。粒度：
    门派 → 代表人物 → 普通斗技 → 特殊斗技 → 特殊物品 → 特殊武器/器物 → 传承异火

资料来源
--------
本文件的人物 / 斗技 / 器物 / 异火归属，来自公开权威整理资料与游戏反编译资源，
逐条标在 ``sources`` 里（编号对应 docs/斗破门派系统_权威资料与数据字典.md 第 0 节）：
    S1 百度百科斗技表   S2/S3 各方势力介绍(中)(下)   S4 中文百科势力结构+天鼎榜
    S5 搜狗百科异火(人-火对应)   S6 搜狗百科天鼎榜   S7 萌娘百科模板
    S8 陀舍古帝玉/萧族/陀舍古帝词条   S9 功法斗技介绍/各派压箱底宝物
    G1 本仓反编译资源 D:/AI/doupo/hy_text
标 ``[游戏原创]`` 的为游戏自造、原著无同名设定。

字段
----
    name/tier/pool/base   名称 / 分期 / 卡池 / 据点
    npcs                  代表人物（姓名（身份））
    skills                普通功法斗技（入道可学）
    special_skills        特殊斗技：[{name, rank, note, unlock_lv}]
    items                 特殊物品
    relics                特殊武器 / 器物 / 阵法 / 信物
    flames                传承异火（带榜位与持有人）
    starter               {skill, special, item, relic} 入道发放
    weight                抽取权重
    unlock_lv             该宗门进入卡池的等级门槛
    sparse                True = 原著/游戏对该派斗技记载稀薄（系统里可只给物品线）

⚠️ 本模块只提供数据与纯函数，**不修改 player 之外的任何状态**；
   接入 core.create_player / commands.cmd_enter / card 的工作留给下一轮，
   因此现有 11 套已验收测试完全不受影响。
"""
from __future__ import annotations

import random

TIERS = ("early", "mid", "late")
POOLS = ("starter", "advanced", "hidden")

#: 每个池的等级门槛（建议值，可调）
POOL_UNLOCK = {"starter": 1, "advanced": 40, "hidden": 90}

#: 特殊斗技分阶解锁等级（建议值，正好复用现有「焚血散升 5 级」机制）
SPECIAL_UNLOCK_STEPS = (20, 40, 60, 80)


def _sp(name, rank, note, unlock_lv=20):
    return {"name": name, "rank": rank, "note": note, "unlock_lv": int(unlock_lv)}


FACTIONS: dict[str, dict] = {
    # ---------------------------------------------------------------- 新手池
    "xiaojia": {
        "name": "萧家", "tier": "early", "pool": "starter", "base": "乌坦城",
        "npcs": ["萧战（族长）", "萧鼎", "萧厉", "萧玉", "萧薰儿（寄居，古族）"],
        "skills": ["狂狮怒罡（玄阶中，仅族长可修）", "炼火焚（黄阶高，萧家最顶尖火功法）"],
        "special_skills": [
            _sp("萧族族纹", "—", "九笔暗红族纹，危急时血脉暴涨 [S8]"),
            _sp("天火三玄变", "秘法", "萧玄所创，四步含族纹修法 [S8][S9]", 60),
        ],
        "items": ["三枚萧族印信 [G1]", "萧家密室 [G1]", "陀舍古帝玉·萧族碎片 [S8]"],
        "relics": ["萧家后山 / 密室 [G1]", "萧界（与古界相接）[S8]"],
        "flames": ["萧族三种传承异火（紫/赤/黑白，萧玄引爆）[S8]"],
        "starter": {"skill": "炼火焚", "special": "萧族族纹",
                    "item": "萧族印信", "relic": "萧家密室"},
        "weight": 12, "unlock_lv": 1, "sparse": False,
        "sources": ["S1", "S3", "S8", "S9", "G1"],
    },
    "yunlanzong": {
        "name": "云岚宗", "tier": "early", "pool": "starter", "base": "云岚山",
        "npcs": ["云破天（创始人）", "云山（上任宗主/斗宗）", "云韵（宗主/斗皇）",
                 "纳兰嫣然（少宗主）", "云棱（大长老/斗王）", "云督", "云刹"],
        "skills": ["青木剑诀（玄阶低）", "爆步（玄阶中，云韵所赠）"],
        "special_skills": [
            _sp("天道神雷剑诀", "—", "云棱绝学，[游戏原创] 原著无同名设定 [G1]", 40),
            _sp("万剑归宗", "—", "宗门合击，[游戏原创] [G1]", 20),
        ],
        "items": ["三年之约 [G1]", "云岚宗门规 [G1]"],
        "relics": ["天刑台 [G1]", "护宗大阵（阵眼「执法弟子」）[G1]", "云岚宗守护兽 [G1]"],
        "flames": [],
        "starter": {"skill": "青木剑诀", "special": "万剑归宗",
                    "item": "云岚宗门规", "relic": "天刑台"},
        "weight": 12, "unlock_lv": 1, "sparse": False,
        "sources": ["S1", "S3", "G1"],
    },
    "lianyao_gonghui": {
        "name": "炼药师公会（加玛）", "tier": "early", "pool": "starter", "base": "黑岩城 / 帝都",
        "npcs": ["丹王古河（丹堂堂主）", "法犸"],
        "skills": ["炼药术与丹方 [S4]", "炼药师品阶考核 [G1]"],
        "special_skills": [_sp("丹会", "—", "中州丹塔主办、公会参与的炼药大比 [S2]", 60)],
        "items": ["丹方 [G1]", "紫云洞药方 [G1]", "筑基灵液 / 增气散 / 聚气散 [S7]"],
        "relics": ["药鼎（天鼎榜体系）[S6]"],
        "flames": [],
        "starter": {"skill": "炼药术", "special": "丹会",
                    "item": "丹方", "relic": "药鼎"},
        "weight": 10, "unlock_lv": 1, "sparse": False,
        "sources": ["S2", "S4", "S6", "S7", "G1"],
    },
    "mojia": {
        "name": "墨家（云岚宗外门）", "tier": "early", "pool": "starter", "base": "帝都·墨家",
        "npcs": ["墨承（云岚宗外门执事）", "墨冉"],
        "skills": [],
        "special_skills": [_sp("灭生门机关", "—", "[游戏原创] 凑齐 4 枚太极残片方可开启 [G1]", 20)],
        "items": ["4 枚太极残片 [G1]"],
        "relics": ["灭生门 [G1]", "墨家暗道 [G1]", "墨承之殿 [G1]"],
        "flames": [],
        "starter": {"skill": "墨家暗道身法", "special": "灭生门机关",
                    "item": "太极残片", "relic": "灭生门"},
        "weight": 8, "unlock_lv": 1, "sparse": True,
        "sources": ["G1", "S7"],
    },
    "sherenzu": {
        "name": "蛇人族", "tier": "early", "pool": "starter", "base": "塔戈尔大沙漠·蛇人禁地",
        "npcs": ["美杜莎/彩鳞（女王）", "青鳞（圣女，后入天蛇府）", "月媚", "墨巴斯", "炎刺"],
        "skills": ["蛇人族法阵（半蛇人血统方可启动）[G1]"],
        "special_skills": [
            _sp("碧蛇三花瞳", "瞳术", "青鳞专属，可收服蛇类魔兽 / 破魂殿隐身 [G1][S4]", 40),
            _sp("七彩吞天蟒进化", "—", "借异火进化灵魂、脱壳凝新身 [G1]", 60),
        ],
        "items": ["七彩吞天蟒 [G1]", "七彩蛇鳞 [G1]", "青莲座 / 地火莲子 [S4]"],
        "relics": ["蛇人禁地 [G1]", "封印术（曾封印冰皇）[G1]"],
        "flames": ["青莲地心火(19)：蛇人族守护/争夺，血脉阴寒与异火相斥 [G1][S5]"],
        "starter": {"skill": "蛇人族法阵", "special": "碧蛇三花瞳",
                    "item": "七彩蛇鳞", "relic": "蛇人禁地"},
        "weight": 10, "unlock_lv": 1, "sparse": False,
        "sources": ["S4", "S5", "S7", "G1"],
    },
    "motie": {
        "name": "漠铁佣兵团 / 石漠城", "tier": "early", "pool": "starter", "base": "石漠城",
        "npcs": ["萧鼎（创建者）", "萧厉（创建者）", "冰皇海波东", "青鳞（原侍女）"],
        "skills": ["冰皇冰系斗技 [G1]"],
        "special_skills": [_sp("寒冰屏障", "—", "[游戏原创] 冰皇拦云山所使 [G1]", 40)],
        "items": ["玄龙丹药方（六品，破封印用）[G1]", "素心丹丹方 [G1]",
                  "塔戈尔大沙漠地图 / 地图残片 [G1]"],
        "relics": ["试炼之塔（九层、守卫 500 年、顶层蛇人月媚、5000 金门票）[G1]"],
        "flames": [],
        "starter": {"skill": "冰皇冰系斗技", "special": "寒冰屏障",
                    "item": "塔戈尔大沙漠地图", "relic": "试炼之塔"},
        "weight": 10, "unlock_lv": 1, "sparse": False,
        "sources": ["S3", "S4", "G1"],
    },
    "langtou": {
        "name": "狼头佣兵团 / 万药斋", "tier": "early", "pool": "starter", "base": "魔兽山脉·紫云洞",
        "npcs": ["穆蛇", "穆力"],
        "skills": [],
        "special_skills": [],
        "items": ["紫云洞药方（两派争夺物）[G1]"],
        "relics": ["紫云洞 [G1]"],
        "flames": [],
        "starter": {"skill": "佣兵围猎", "special": "—",
                    "item": "紫云洞药方", "relic": "紫云洞"},
        "weight": 6, "unlock_lv": 1, "sparse": True,
        "sources": ["S7", "G1"],
    },
    "duzong": {
        "name": "毒宗（出云帝国）", "tier": "early", "pool": "starter", "base": "出云帝国",
        "npcs": ["天毒女/小医仙（宗主）", "五位斗皇长老"],
        "skills": ["毒属性功法（毒素融入斗气）[S3]"],
        "special_skills": [
            _sp("厄难毒体", "体质", "天生毒体，[S4]；冰河谷另研有后天厄难毒体 [S9]", 60),
        ],
        "items": ["血莲精 [S4]"],
        "relics": ["万蝎门（敌对）[S3]"],
        "flames": ["幽冥毒火(20) / 阴阳双炎(21)（后期毒体相关）[S7]"],
        "starter": {"skill": "毒属性功法", "special": "厄难毒体",
                    "item": "血莲精", "relic": "毒宗令"},
        "weight": 9, "unlock_lv": 1, "sparse": False,
        "sources": ["S3", "S4", "S7", "S9"],
    },
    "tianshefu": {
        "name": "天蛇府（天蛇帝国）", "tier": "early", "pool": "starter", "base": "天蛇帝国",
        "npcs": ["青鳞（圣女）", "青长老"],
        "skills": [],
        "special_skills": [_sp("碧蛇三花瞳", "瞳术", "圣女专属，可收服蛇类魔兽 [S4]", 40)],
        "items": ["阴阳玄龙丹（七品，被血宗范痨抢走）[S3]"],
        "relics": ["天蛇府圣殿 [S4]"],
        "flames": [],
        "starter": {"skill": "蛇系驭兽术", "special": "碧蛇三花瞳",
                    "item": "阴阳玄龙丹", "relic": "天蛇府圣殿"},
        "weight": 8, "unlock_lv": 1, "sparse": True,
        "sources": ["S3", "S4"],
    },
    "mulangu": {
        "name": "慕兰谷（慕兰帝国）", "tier": "early", "pool": "starter", "base": "慕兰帝国",
        "npcs": ["虎头人（三长老）", "狮头人（三长老）", "熊头人（三长老）"],
        "skills": [],
        "special_skills": [
            _sp("三兽蛮荒决", "地阶中", "镇派绝学，三长老合击可抗斗宗 [S9]", 40),
        ],
        "items": [],
        "relics": ["慕兰谷三长老阵 [S4]"],
        "flames": [],
        "starter": {"skill": "三兽蛮荒决·基础", "special": "三兽蛮荒决",
                    "item": "慕兰谷令", "relic": "三长老阵"},
        "weight": 7, "unlock_lv": 1, "sparse": True,
        "sources": ["S4", "S9"],
    },
    # ---------------------------------------------------------------- 进阶池
    "jianan": {
        "name": "迦南学院", "tier": "mid", "pool": "advanced", "base": "黑角域",
        "npcs": ["邙天尺（创建者/内院院长，雷族长老）", "琥乾（外院副院长）",
                 "苏千（内院大长老）", "千百二老（守护者）", "若琳（外院导师）"],
        "skills": ["狮虎碎金吟（玄阶高，藏书阁）[S7]"],
        "special_skills": [_sp("天焚炼气塔淬炼", "—", "塔下陨落心炎持续淬炼斗气 [S4]", 40)],
        "items": ["地灵丹（六品，收服陨落心炎必备）[S9]", "陀舍古帝玉·洞府线索 [S8]"],
        "relics": ["天焚炼气塔 [S4]", "古帝洞府（塔底）[S8]"],
        "flames": ["陨落心炎(14)：塔下封印，邙天尺放置 [S4][S5]"],
        "starter": {"skill": "狮虎碎金吟", "special": "天焚炼气塔淬炼",
                    "item": "地灵丹", "relic": "天焚炼气塔"},
        "weight": 7, "unlock_lv": 40, "sparse": False,
        "sources": ["S3", "S4", "S7", "S8", "S9"],
    },
    "fengleige": {
        "name": "风雷阁", "tier": "mid", "pool": "advanced", "base": "中州·四方阁",
        "npcs": ["雷尊者（阁主，三星斗尊巅峰）", "沈云", "费天"],
        "skills": ["三千雷动（地阶低，镇阁身法：雷闪→雷瞬→三千雷）[S1]"],
        "special_skills": [
            _sp("三千雷幻身", "地阶高", "镇阁之宝，本体不死分身不灭 [S1]", 60),
        ],
        "items": ["三千雷动残卷 [S3]", "净莲妖火残图（曾被血宗范凌拍得）[S3]"],
        "relics": ["风雷阁雷坛 [S2]"],
        "flames": [],
        "starter": {"skill": "三千雷动", "special": "三千雷幻身",
                    "item": "三千雷动残卷", "relic": "风雷阁雷坛"},
        "weight": 7, "unlock_lv": 40, "sparse": False,
        "sources": ["S1", "S2", "S3", "G1"],
    },
    "fenyangu": {
        "name": "焚炎谷", "tier": "mid", "pool": "advanced", "base": "中州·三谷",
        "npcs": ["焚炎老祖（创始人，远古五至强）", "唐震（谷主）", "火云老祖",
                 "唐火儿", "吴辰", "赤火长老"],
        "skills": ["青冥幽炎决（传承功法，可用九龙雷罡火）[S9]"],
        "special_skills": [
            _sp("天火三玄变", "秘法", "萧玄所创、传焚炎老祖，燃异火暴涨战力 [S3][S9]", 60),
        ],
        "items": ["火菩丹（七品，与萧炎合炼）[S6]"],
        "relics": ["山熔鼎（天鼎榜 12，唐震所有）[S6]"],
        "flames": ["九龙雷罡火(12)：谷主唐震 [S5]"],
        "starter": {"skill": "青冥幽炎决", "special": "天火三玄变",
                    "item": "火菩丹", "relic": "山熔鼎"},
        "weight": 7, "unlock_lv": 40, "sparse": False,
        "sources": ["S2", "S3", "S5", "S6", "S9"],
    },
    "binghegu": {
        "name": "冰河谷", "tier": "mid", "pool": "advanced", "base": "中州·三谷",
        "npcs": ["冰尊者冰河（谷主）", "天霜子（大长老）", "天蛇", "冰元", "冰鹤"],
        "skills": ["冻天掌 [S2]"],
        "special_skills": [
            _sp("冰尊劲", "—", "冻结对手经脉 [S9]", 40),
            _sp("后天厄难毒体", "体质", "谷主冰河豢养研究 [S9]", 60),
        ],
        "items": [],
        "relics": ["冰河谷冰狱 [S2]"],
        "flames": [],
        "starter": {"skill": "冻天掌", "special": "冰尊劲",
                    "item": "冰河谷令", "relic": "冰河谷冰狱"},
        "weight": 6, "unlock_lv": 40, "sparse": False,
        "sources": ["S2", "S9"],
    },
    "tianmingzong": {
        "name": "天冥宗", "tier": "mid", "pool": "advanced", "base": "中州·二宗",
        "npcs": ["天冥子（宗主）", "天冥老妖（太上长老）", "易尘（少主）", "辰闲", "辰天南"],
        "skills": [],
        "special_skills": [
            _sp("天冥修罗手", "地阶高", "镇宗绝学，实际威力可比肩天阶 [S1]", 60),
        ],
        "items": [],
        "relics": ["天冥宗杀伐阵 [S2]"],
        "flames": [],
        "starter": {"skill": "天冥宗基础杀伐术", "special": "天冥修罗手",
                    "item": "天冥宗令", "relic": "天冥宗杀伐阵"},
        "weight": 6, "unlock_lv": 40, "sparse": True,
        "sources": ["S1", "S2"],
    },
    "huazong": {
        "name": "花宗", "tier": "mid", "pool": "advanced", "base": "中州·二宗",
        "npcs": ["云韵（宗主，八星斗尊）", "花玉（前任宗主）", "青仙子", "华仙子",
                 "纳兰嫣然（少宗主）"],
        "skills": ["花宗传承（只收女弟子）[S2]"],
        "special_skills": [_sp("花宗双太上长老阵", "—", "中级/高级半圣坐镇 [S2]", 60)],
        "items": [],
        "relics": ["花宗玉牌 [S2]"],
        "flames": [],
        "starter": {"skill": "花宗传承", "special": "花宗双太上长老阵",
                    "item": "花宗玉牌", "relic": "花宗玉牌"},
        "weight": 6, "unlock_lv": 40, "sparse": True,
        "sources": ["S2", "S3"],
    },
    "danta": {
        "name": "丹塔", "tier": "mid", "pool": "advanced", "base": "圣丹城",
        "npcs": ["丹塔老祖（九品玄丹所化，六星斗圣）", "林老怪（小丹塔大长老）",
                 "玄空子", "玄衣", "天雷子（三巨头）"],
        "skills": ["丹会 / 七色八品丹雷（进小丹塔门槛）[S2]"],
        "special_skills": [
            _sp("小丹塔大长老院表决", "—", "十位长老投票决定丹塔大事 [S4]", 60),
        ],
        "items": ["九品玄丹 [S2]", "天鼎榜药鼎 [S6]"],
        "relics": ["星域（独立空间，封印异火）[S4]", "小丹塔 [S2]"],
        "flames": ["三千焱炎火(9)：星域禁锢，丹塔所有 [S4][S5]"],
        "starter": {"skill": "丹会炼药术", "special": "小丹塔大长老院表决",
                    "item": "九品玄丹", "relic": "星域"},
        "weight": 6, "unlock_lv": 40, "sparse": False,
        "sources": ["S2", "S4", "S5", "S6"],
    },
    "xingyunge": {
        "name": "星陨阁", "tier": "mid", "pool": "advanced", "base": "中州·四方阁",
        "npcs": ["药圣药尘（阁主）", "风尊者风闲（副阁主）", "萧炎（少阁主）"],
        "skills": ["药尘炼药术（八品巅峰炼药宗师）[S4]"],
        "special_skills": [_sp("星陨阁大阵", "—", "四方阁护阁阵 [S4]", 60)],
        "items": ["帝品丹方 [G1]", "真阳丹（帝品）[G1]"],
        "relics": ["黑魔鼎（天鼎榜 8，药尘所有）[S6]", "纳戒 [G1]"],
        "flames": ["骨灵冷火(11)：药尘本命，后传萧炎 [S5]"],
        "starter": {"skill": "药尘炼药术", "special": "星陨阁大阵",
                    "item": "帝品丹方", "relic": "黑魔鼎"},
        "weight": 5, "unlock_lv": 40, "sparse": False,
        "sources": ["S2", "S4", "S5", "S6", "G1"],
    },
    "hundian": {
        "name": "魂殿 / 魂族", "tier": "mid", "pool": "advanced", "base": "中州·一殿",
        "npcs": ["魂灭生（殿主）", "副殿主", "大天尊", "骨幽圣者", "血河尊者",
                 "摘星老鬼", "慕骨老人", "鹜护法", "铁护法"],
        "skills": ["摄魂 / 控魂 / 隐身 [G1]"],
        "special_skills": [
            _sp("灵魂体搜捕", "—", "满大陆搜捕灵魂体、控制对手 [G1][S2]", 60),
        ],
        "items": ["陀舍古帝玉（集齐八块）[S8]", "海心焰（韩枫→慕骨老人）[S5]"],
        "relics": ["天罡殿/地煞殿/分殿 [S2]", "噬魂大殿 / 摄魂台 / 幽都 [G1]"],
        "flames": ["虚无吞炎(2)子火：魂灭生 / 天池子火：魂虚子 [S5]"],
        "starter": {"skill": "摄魂术", "special": "灵魂体搜捕",
                    "item": "魂殿令", "relic": "噬魂大殿"},
        "weight": 4, "unlock_lv": 40, "sparse": False,
        "sources": ["S2", "S5", "S8", "G1"],
    },
    "moyangu": {
        "name": "魔炎谷（黑角域）", "tier": "mid", "pool": "advanced", "base": "黑角域",
        "npcs": ["地魔老鬼（创始人，七星斗宗）", "方言（大长老）", "鹰爪老人（四长老）"],
        "skills": ["弄焰诀（地魔老鬼改良，三兽火融合化生火）[S3][S9]"],
        "special_skills": [
            _sp("天妖傀炼制秘法", "秘法", "可制造升级型战斗傀儡 [S3][S9]", 60),
        ],
        "items": ["菩提化体涎（拍卖争夺）[S3]"],
        "relics": ["天妖傀（地妖傀→天妖傀→北王）[S9]"],
        "flames": ["化生火（伪异火）[S7]"],
        "starter": {"skill": "弄焰诀", "special": "天妖傀炼制秘法",
                    "item": "菩提化体涎", "relic": "天妖傀"},
        "weight": 5, "unlock_lv": 40, "sparse": False,
        "sources": ["S3", "S7", "S9"],
    },
    "xuezong": {
        "name": "血宗（黑角域）", "tier": "mid", "pool": "advanced", "base": "黑角域",
        "npcs": ["范痨（宗主，黑榜第五）", "范凌（少宗主）"],
        "skills": ["阴寒属性功法（被异火所制）[S4]"],
        "special_skills": [],
        "items": ["阴阳玄龙丹（抢自天蛇府）[S3]", "三千雷动 [S3]", "净莲妖火残图 [S3]"],
        "relics": ["血宗残破地图 [S4]"],
        "flames": [],
        "starter": {"skill": "阴寒功法", "special": "—",
                    "item": "阴阳玄龙丹", "relic": "血宗残破地图"},
        "weight": 4, "unlock_lv": 40, "sparse": True,
        "sources": ["S3", "S4"],
    },
    # ---------------------------------------------------------------- 隐藏池
    "guzu": {
        "name": "古族", "tier": "late", "pool": "hidden", "base": "古界",
        "npcs": ["古元（族长，九星斗圣巅峰）", "萧薰儿（古族大小姐）", "黑湮军"],
        "skills": ["古圣宝鉴（天阶低，含吞天纳地）[S1]"],
        "special_skills": [
            _sp("帝印决", "地阶高", "镇族绝学，开山/翻海/覆地/湮天/古帝五印 [S1]", 60),
            _sp("大寂灭指", "天阶低", "古族秘传，指劲所过空间崩裂 [S1]", 80),
        ],
        "items": ["陀舍古帝玉·古族碎片 [S8]", "古界 [S8]"],
        "relics": ["护族大阵 [S9]", "古族大殿 [G1]"],
        "flames": ["金帝焚天炎(4)：古族传承火，萧薰儿持有 [S5]"],
        "starter": {"skill": "古圣宝鉴", "special": "帝印决",
                    "item": "古族玉佩", "relic": "古界"},
        "weight": 2, "unlock_lv": 90, "sparse": False,
        "sources": ["S1", "S4", "S5", "S8", "S9", "G1"],
    },
    "xiaozu": {
        "name": "萧族 / 天墓", "tier": "late", "pool": "hidden", "base": "萧界 → 乌坦城",
        "npcs": ["萧玄（前族长）", "萧晨"],
        "skills": ["天火三玄变（萧玄所创，四步含族纹修法）[S8][S9]"],
        "special_skills": [
            _sp("萧族族纹", "—", "九笔暗红，危急时血脉暴涨 [S8]", 60),
            _sp("斗帝血脉觉醒", "—", "天墓萧玄血线传承 [S8][G1]", 90),
        ],
        "items": ["陀舍古帝玉·萧族碎片 [S8]", "远古虫皇衣（萧玄赠）[S9]"],
        "relics": ["天墓 [G1]", "萧界（与古界相接）[S8]"],
        "flames": ["萧族三种传承异火（紫/赤/黑白，萧玄自爆引爆）[S8]"],
        "starter": {"skill": "天火三玄变", "special": "萧族族纹",
                    "item": "陀舍古帝玉碎片", "relic": "天墓"},
        "weight": 2, "unlock_lv": 90, "sparse": False,
        "sources": ["S8", "S9", "G1"],
    },
    "yanzu": {
        "name": "炎族", "tier": "late", "pool": "hidden", "base": "炎界",
        "npcs": ["炎烬（族长）", "火稚", "火炫", "火耀"],
        "skills": ["五火传承 [S5]"],
        "special_skills": [_sp("护族大阵", "—", "可召斗帝先祖残魂 [S9]", 90)],
        "items": ["陀舍古帝玉·炎族碎片 [S8]"],
        "relics": ["炎界 [S4]"],
        "flames": ["八荒破灭焱(6)/九幽金祖火(7)/红莲业火(8)/火云水炎(16)/火山石焰(17) [S5]"],
        "starter": {"skill": "五火传承", "special": "护族大阵",
                    "item": "炎族火令", "relic": "炎界"},
        "weight": 2, "unlock_lv": 90, "sparse": False,
        "sources": ["S4", "S5", "S8", "S9"],
    },
    "yaozu": {
        "name": "药族", "tier": "late", "pool": "hidden", "base": "药界",
        "npcs": ["药丹（族长，七星斗圣）", "药天", "药星极"],
        "skills": ["药典 / 炼药传承 [S4]"],
        "special_skills": [
            _sp("化天药阵", "—", "可召斗帝先祖残魂（药帝残魂）[S9]", 90),
        ],
        "items": ["陀舍古帝玉·药族碎片 [S8]", "药鼎 [S9]"],
        "relics": ["药界 [S4]"],
        "flames": ["九幽风炎(10)：药星极；龟灵地火(13)：药天 [S5]"],
        "starter": {"skill": "药典", "special": "化天药阵",
                    "item": "药族丹方", "relic": "药鼎"},
        "weight": 2, "unlock_lv": 90, "sparse": False,
        "sources": ["S4", "S5", "S8", "S9"],
    },
    "hunzu": {
        "name": "魂族", "tier": "late", "pool": "hidden", "base": "魂界",
        "npcs": ["魂天帝（族长，后成斗帝）", "魂虚子（首席炼药师）"],
        "skills": ["吞噬血脉延续 [S4]"],
        "special_skills": [_sp("虚无吞炎", "异火", "榜 2 本体，魂族吞族之战依仗 [S5]", 90)],
        "items": ["陀舍古帝玉（集齐八块）[S8]", "帝品雏丹 [S8]"],
        "relics": ["魂殿（明面势力）[S4]", "葬天山脉 [S4]"],
        "flames": ["虚无吞炎(2) [S5]"],
        "starter": {"skill": "吞噬血脉术", "special": "虚无吞炎",
                    "item": "陀舍古帝玉", "relic": "魂殿"},
        "weight": 1, "unlock_lv": 90, "sparse": False,
        "sources": ["S4", "S5", "S8"],
    },
    "taixugulong": {
        "name": "太虚古龙族", "tier": "late", "pool": "hidden", "base": "古龙岛",
        "npcs": ["紫研（族长）", "烛坤（老族长）", "四大龙岛龙王"],
        "skills": [],
        "special_skills": [
            _sp("龙凰古甲", "防身技", "紫研注入龙凰古血，古龙专属 [S7]", 90),
        ],
        "items": ["龙凰本源果 [S9]"],
        "relics": ["龙魂鼎（天鼎榜 4，龙族斗帝所造）[S6]", "古龙岛 [G1]"],
        "flames": [],
        "starter": {"skill": "古龙肉身术", "special": "龙凰古甲",
                    "item": "龙凰本源果", "relic": "古龙岛"},
        "weight": 2, "unlock_lv": 90, "sparse": False,
        "sources": ["S4", "S6", "S7", "S9", "G1"],
    },
    "jiuyou": {
        "name": "九幽地冥蟒族", "tier": "late", "pool": "hidden", "base": "九幽地冥蟒族地",
        "npcs": ["妖暝（族长）", "黄泉妖圣"],
        "skills": ["黄泉指（天阶低）[S1]"],
        "special_skills": [
            _sp("黄泉掌", "天阶中", "黄泉三绝之一 [S1]", 80),
            _sp("黄泉天怒", "天阶高", "黄泉妖圣最强杀招，灵魂攻击 [S1]", 90),
        ],
        "items": ["黄泉石碑 [S9]"],
        "relics": ["黄泉妖圣传承地 [S9]"],
        "flames": [],
        "starter": {"skill": "黄泉指", "special": "黄泉掌",
                    "item": "黄泉石碑", "relic": "黄泉妖圣传承地"},
        "weight": 2, "unlock_lv": 90, "sparse": False,
        "sources": ["S1", "S4", "S9"],
    },
    "tianfu": {
        "name": "天府联盟", "tier": "late", "pool": "hidden", "base": "中州",
        "npcs": ["药尘（盟主）", "萧炎（少盟主）", "丹塔老祖", "萧晨", "神农老人",
                 "火云老祖", "青仙子", "小医仙", "青鳞"],
        "skills": ["星陨阁 + 丹塔 + 花宗 + 焚炎谷 四派功法合流 [S3][S8]"],
        "special_skills": [_sp("联盟大阵", "—", "为对抗魂殿而结盟 [S3]", 90)],
        "items": [],
        "relics": ["天府联盟总坛 [S3]"],
        "flames": [],
        "starter": {"skill": "四派合流功法", "special": "联盟大阵",
                    "item": "天府盟令", "relic": "天府联盟总坛"},
        "weight": 1, "unlock_lv": 90, "sparse": True,
        "sources": ["S3", "S8"],
    },
}


# ---------------------------------------------------------------------------
# 纯函数（不读写文件、不 import 运行时）
# ---------------------------------------------------------------------------
def all_factions() -> dict[str, dict]:
    return FACTIONS


def get(fid: str) -> dict | None:
    return FACTIONS.get(fid)


def by_tier(tier: str) -> dict[str, dict]:
    return {k: v for k, v in FACTIONS.items() if v["tier"] == tier}


def by_pool(pool: str, lv: int | None = None) -> dict[str, dict]:
    out = {k: v for k, v in FACTIONS.items() if v["pool"] == pool}
    if lv is not None:
        out = {k: v for k, v in out.items() if int(v["unlock_lv"]) <= int(lv)}
    return out


def random_faction(pool: str = "starter", lv: int | None = None, rng=None) -> str | None:
    """按 weight 抽一个宗门 id；rng 可注入（测试用 lambda: 0.0 / 1.0）。"""
    r = rng or random.random
    pool_map = by_pool(pool, lv if lv is not None else POOL_UNLOCK.get(pool, 1))
    if not pool_map:
        return None
    ids = list(pool_map)
    weights = [max(0, int(pool_map[i]["weight"])) for i in ids]
    total = sum(weights)
    if total <= 0:
        return None
    pick = r() * total
    acc = 0
    for fid, w in zip(ids, weights):
        acc += w
        if pick < acc:
            return fid
    return ids[-1]


def starter_kit(fid: str) -> dict:
    """入道发放的 4 项（普通斗技 / 特殊斗技 / 特殊物品 / 特殊器物）。"""
    f = FACTIONS.get(fid)
    if not f:
        return {}
    kit = dict(f["starter"])
    kit["faction"] = fid
    kit["faction_name"] = f["name"]
    return kit


def assign_faction(p: dict, rng=None, pool: str = "starter", lv: int | None = None) -> dict:
    """把宗门写进 player dict（**只增字段，不改既有字段、不动 schema**）。"""
    level = int(lv if lv is not None else p.get("lv", 1))
    fid = random_faction(pool=pool, lv=level, rng=rng)
    if not fid:
        return {}
    kit = starter_kit(fid)
    p.update(kit)
    return kit


def faction_of(p: dict) -> dict | None:
    """读玩家当前宗门；未分配返回 None。"""
    return FACTIONS.get(str(p.get("faction") or ""))


def special_skills_at(fid: str, lv: int) -> list[dict]:
    """按等级返回已解锁的特殊斗技。"""
    f = FACTIONS.get(fid)
    if not f:
        return []
    return [s for s in f["special_skills"] if int(lv) >= int(s["unlock_lv"])]


def validate() -> list[str]:
    """数据自检：返回问题清单，空列表 = 数据完整（供 test_factions.py 断言）。"""
    problems: list[str] = []
    required = ("name", "tier", "pool", "base", "npcs", "skills", "special_skills",
                "items", "relics", "flames", "starter", "weight", "unlock_lv", "sources")
    for fid, f in FACTIONS.items():
        for k in required:
            if k not in f:
                problems.append("%s 缺字段 %s" % (fid, k))
        if f.get("tier") not in TIERS:
            problems.append("%s tier 非法" % fid)
        if f.get("pool") not in POOLS:
            problems.append("%s pool 非法" % fid)
        if not f.get("npcs"):
            problems.append("%s 无代表人物" % fid)
        if int(f.get("weight") or 0) <= 0:
            problems.append("%s 权重非正" % fid)
        if not f.get("sources"):
            problems.append("%s 无来源标注" % fid)
        kit = f.get("starter") or {}
        for k in ("skill", "special", "item", "relic"):
            if not kit.get(k):
                problems.append("%s starter.%s 为空" % (fid, k))
        for s in f.get("special_skills") or []:
            if not s.get("name") or "unlock_lv" not in s:
                problems.append("%s 特殊斗技字段不全" % fid)
    return problems
