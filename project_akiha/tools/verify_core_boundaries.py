"""Automatic static gate for core imports and concrete platform execution."""

from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN = (
    "PySide6",
    "ctypes",
    "subprocess",
    "winreg",
    "win32",
    "importlib",
    "project_akiha.app",
    "project_akiha.ui",
    "project_akiha.services",
    "project_akiha.providers",
    "project_akiha.database",
    "project_akiha.integrations",
    "project_akiha.tools",
)
OUTER_LAYERS = {
    prefix.split(".")[-1] for prefix in FORBIDDEN if prefix.startswith("project_akiha.")
}


def violations(source: str) -> list[str]:
    tree = ast.parse(source)
    found = []
    os_names = {"os"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os":
                    os_names.add(alias.asname or alias.name)
        modules = (
            [node.module or ""]
            if isinstance(node, ast.ImportFrom)
            else (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else []
            )
        )
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level and module.split(".")[0] in OUTER_LAYERS:
                found.append(f"line {node.lineno}: relative outer-layer import")
            if module == "project_akiha" or (node.level and not module):
                if any(
                    alias.name in OUTER_LAYERS or alias.name == "*"
                    for alias in node.names
                ):
                    found.append(f"line {node.lineno}: outer-layer member import")
        for module in modules:
            if any(
                module == prefix
                or module.startswith(prefix + ".")
                or (prefix == "win32" and module.startswith(prefix))
                for prefix in FORBIDDEN
            ):
                found.append(f"line {node.lineno}: forbidden import {module}")
        if isinstance(node, ast.ImportFrom) and node.module == "os":
            if any(
                alias.name in ("startfile", "system", "popen", "*")
                or alias.name.startswith(("spawn", "exec"))
                for alias in node.names
            ):
                found.append(f"line {node.lineno}: concrete OS execution import")
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in os_names and (
                node.attr in ("startfile", "system", "popen")
                or node.attr.startswith(("spawn", "exec"))
            ):
                found.append(f"line {node.lineno}: concrete OS execution")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "__import__":
                found.append(f"line {node.lineno}: dynamic import")
            if node.func.id == "getattr" and len(node.args) >= 2:
                target, attribute = node.args[:2]
                if (
                    isinstance(target, ast.Name)
                    and target.id in os_names
                    and isinstance(attribute, ast.Constant)
                    and attribute.value in ("startfile", "system", "popen")
                ):
                    found.append(f"line {node.lineno}: concrete OS execution lookup")
    return found


def check_core(root: Path = Path("project_akiha/core")) -> None:
    failures = [
        f"{path}: {finding}"
        for path in sorted(root.rglob("*.py"))
        for finding in violations(path.read_text(encoding="utf-8-sig"))
    ]
    if failures:
        raise AssertionError("\n".join(failures))


if __name__ == "__main__":
    check_core()
    print("Core import/platform boundary: PASS")
