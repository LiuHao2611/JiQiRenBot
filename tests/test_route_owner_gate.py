# -*- coding: utf-8 -*-
"""回归：不得出现**未定义的**裸 `is_owner` 名（2026-11-14 线上事故）。

事故：commit 2f35ed7（文件互传）在追问式保存闸写了 `is_owner(ev.user_id)`，
但本模块通用的是 `_is_owner`，dispatcher 也只 import 了 `allow, normalize`。
结果：主人私聊发任意纯文字 → 走到该闸 → `NameError` → 整个路由崩溃、机器人不回复。

检查口径（2026-11-14 修正）：按**作用域**判定，不是见到 `is_owner` 就报。
模块里本来就有合法用法 —— `_pic_menu_render` 里有局部变量
`is_owner = _is_owner(user_id) and ...`，对它取 Load 完全正确。
上一版无脑收集所有 `ast.Name(id="is_owner")`，把这些局部变量也当成违规，
用例本身恒红（等于没守住任何东西，见 prove-it：测试必须能红也能绿）。
"""
import ast

INIT_REL = "src/plugins/qq_bridge/__init__.py"


def _undefined_is_owner_lines(source: str) -> list[tuple[int, int]]:
    """返回 `is_owner` 被当作**未绑定名**读取的位置（行,列）。

    规则：某个函数（或模块顶层）内出现对 `is_owner` 的 Load，但该作用域从未
    绑定过 `is_owner`（参数 / 赋值 / import）→ 记为违规。
    """
    tree = ast.parse(source)

    def bound_names(node) -> set[str]:
        """该作用域自己绑定的名字（含参数、赋值、for/with 目标、嵌套 import）。"""
        names: set[str] = set()
        args = getattr(node, "args", None)
        if args is not None:
            for a in list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs):
                names.add(a.arg)
            if args.vararg:
                names.add(args.vararg.arg)
            if args.kwarg:
                names.add(args.kwarg.arg)
        # 只看本作用域（不钻进嵌套 def/lambda），嵌套作用域各自负责自己
        stack = list(node.body)
        while stack:
            cur = stack.pop()
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(cur, ast.Name) and isinstance(cur.ctx, ast.Store):
                names.add(cur.id)
            if isinstance(cur, (ast.Import, ast.ImportFrom)):
                for alias in cur.names:
                    names.add((alias.asname or alias.name).split(".")[0])
            stack.extend(ast.iter_child_nodes(cur))
        return names

    def loads(node) -> list[tuple[int, int]]:
        out: list[tuple[int, int]] = []
        stack = list(node.body)
        while stack:
            cur = stack.pop()
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(cur, ast.Name) and cur.id == "is_owner" and isinstance(cur.ctx, ast.Load):
                out.append((cur.lineno, cur.col_offset))
            stack.extend(ast.iter_child_nodes(cur))
        return out

    bad: list[tuple[int, int]] = []
    scopes = [tree]
    scopes += [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    for scope in scopes:
        if "is_owner" in bound_names(scope):
            continue
        bad.extend(loads(scope))
    # 同名位置会因嵌套作用域重复命中，去重保序
    return sorted(set(bad))


def test_no_undefined_is_owner_in_plugin():
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / INIT_REL).read_text(encoding="utf-8")
    bad = _undefined_is_owner_lines(src)
    assert bad == [], (
        "发现未定义的裸 is_owner 引用（行,列）=%r；本模块应使用 _is_owner()" % (bad,)
    )


def test_checker_catches_the_original_bug():
    """检查器自检：还原事故现场必须报红（否则这道闸等于没装）。"""
    broken = (
        "def _route(ev):\n"
        "    if is_owner(ev.user_id):\n"
        "        return 'ok'\n"
    )
    assert _undefined_is_owner_lines(broken) == [(2, 7)]


def test_checker_allows_local_variable():
    """局部变量 `is_owner = _is_owner(...)` 是合法用法，不得误报。"""
    ok = (
        "def _pic_menu_render(user_id):\n"
        "    is_owner = _is_owner(user_id)\n"
        "    if is_owner:\n"
        "        return 'owner'\n"
        "    return 'user'\n"
    )
    assert _undefined_is_owner_lines(ok) == []


def test_is_owner_helper_exists():
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / INIT_REL).read_text(encoding="utf-8")
    names = {
        n.name for n in ast.walk(ast.parse(src))
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "_is_owner" in names
