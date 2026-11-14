# -*- coding: utf-8 -*-
"""回归：`_route` 里不得出现未定义的裸 `is_owner` 名（2026-11-14 线上事故）。

事故：commit 2f35ed7（文件互传）在追问式保存闸写了 `is_owner(ev.user_id)`，
但本模块通用的是 `_is_owner`（第 ~6841 行定义），dispatcher 也只 import 了
`allow, normalize`。结果：主人私聊发任意纯文字 → 走到该闸 → `NameError` →
整个路由崩溃、机器人不回复。

用 AST 静态检查拦住这类"函数名少个下划线"的未定义名（参数名 `is_owner=True`
是 keyword 节点、属性 `xx.is_owner` 是 Attribute 节点，都不会误报）。
"""
import ast
from pathlib import Path

INIT = Path(__file__).resolve().parents[1] / "src" / "plugins" / "qq_bridge" / "__init__.py"


def test_no_bare_is_owner_name():
    tree = ast.parse(INIT.read_text(encoding="utf-8"))
    bad = [
        (n.lineno, n.col_offset)
        for n in ast.walk(tree)
        if isinstance(n, ast.Name) and n.id == "is_owner"
    ]
    assert bad == [], (
        "发现未定义的裸 is_owner 引用（行,列）=%r；本模块应使用 _is_owner()" % (bad,)
    )


def test_is_owner_helper_exists():
    tree = ast.parse(INIT.read_text(encoding="utf-8"))
    names = {
        n.name for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "_is_owner" in names
