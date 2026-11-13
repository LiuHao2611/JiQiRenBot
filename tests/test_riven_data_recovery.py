# -*- coding: utf-8 -*-
"""紫卡分析事故回归（2026-11-13 19:43，容器日志 wf_riven_ocr_raw 实证）。

事故：OCR 把四条词条**全部读对**，但 data/warframe_items/ 里三张派生表从未落地，
_load_riven_data 静默降级成空字典 → _find_stat 零匹配 → _parse_ocr 返回 None
→ 用户拿到「图可能太小、被裁切」的误导诊断卡。

这三个用例守的是用户真正感受得到的行为：
  1. 词库缺了要显式报错、并告诉用户怎么修，不许静默；
  2. 词库齐了，同一份真实 OCR 文本必须解析出完整卡面（4 条词条 + 武器名）；
  3. 词库缺了，分析入口必须回报真实原因，不能甩锅截图。
"""
from __future__ import annotations

import asyncio

import pytest

from src.plugins.qq_bridge.game_tools import riven

#: 19:43:10 容器日志 wf_riven_ocr_raw: len=91 text=... 的**原文**，不是编造的样本。
REAL_OCR_TEXT = (
    "18Y\n卡帕压力枪 Croni-\nsatipia\n+144.9%多重射击\n"
    "收起武器时弹匣每秒自动\n装填+106.3 %\n+92.4% 射速\n"
    "-82.7% 弹药最大值\n段位10\n523"
)


def test_riven_data_status_detects_missing(tmp_path, monkeypatch) -> None:
    """空数据目录 → 必需文件逐个报缺，ensure 显式抛错且给出修复命令。"""
    monkeypatch.setattr(riven, "_DATA_DIR", tmp_path)
    ok, missing = riven.riven_data_status()
    assert ok is False
    for name in riven.RIVEN_REQUIRED_FILES:
        assert any(name in m for m in missing), f"未报出缺失文件 {name}"
    with pytest.raises(riven.RivenDataUnavailable) as ei:
        riven.ensure_riven_data()
    assert "prepare_warframe_data.py" in str(ei.value)


def test_real_ocr_text_parses_full_card() -> None:
    """词库齐全时，事故现场的 OCR 原文必须解析出 4 条词条 + 武器名。"""
    ok, missing = riven.riven_data_status()
    if not ok:
        pytest.fail(
            "紫卡静态词库缺失，无法验证修复效果："
            + "; ".join(missing)
            + "。请先运行 python scripts/prepare_warframe_data.py"
        )
    riven.ensure_riven_data()
    parsed = riven._parse_ocr(REAL_OCR_TEXT)
    assert parsed is not None, "真实 OCR 文本应解析出完整卡面"
    assert parsed["weapon"] == "Kompressa"
    assert parsed["weapon_zh"] == "卡帕压力枪"
    assert parsed["riven_name"] == "Croni-satipia"
    got = [(s["en"], s["value"], s["sign"]) for s in parsed["stats"]]
    assert ("Multishot", 144.9, "+") in got
    assert ("Reload Speed", 106.3, "+") in got
    assert ("Fire Rate / Attack Speed", 92.4, "+") in got
    assert ("Ammo Maximum", 82.7, "-") in got
    assert len(got) == 4, f"应解析出 4 条词条，实际: {got}"


def test_analyze_full_reports_real_reason_when_data_missing(tmp_path, monkeypatch) -> None:
    """词库缺失时返回真实原因，绝不再输出「图太小/被裁切」的误导文案。"""
    monkeypatch.setattr(riven, "_DATA_DIR", tmp_path)
    text, card = asyncio.run(riven.riven_img_analyze_full(b"not-an-image"))
    assert card is None
    assert "紫卡词库未就绪" in text
    assert "prepare_warframe_data.py" in text
    assert "图可能太小" not in text
    assert "没凑齐" not in text
