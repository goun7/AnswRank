"""AST tarama: test-disi kalan fonksiyonlari bulur."""
import ast
import os
import re
import sys

PKG = "/home/gokun/projects/02_sahis/85-AnswRank/answrank"
TESTS = "/home/gokun/projects/02_sahis/85-AnswRank/tests"
ROOT = "/home/gokun/projects/02_sahis/85-AnswRank"

funcs = {}
for root, _, files in os.walk(PKG):
    for fn in files:
        if not fn.endswith(".py"):
            continue
        path = os.path.join(root, fn)
        rel = os.path.relpath(path, ROOT)
        try:
            src = open(path, encoding="utf-8").read()
            tree = ast.parse(src)
        except Exception as e:
            print(f"PARSE-FAIL {rel}: {e}", file=sys.stderr)
            continue
        end = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("__") and node.name.endswith("__"):
                    continue
                mod = rel.replace("/", ".").removesuffix(".py")
                key = f"{mod}::{node.name}"
                e2 = max((c.end_lineno for c in ast.walk(node) if hasattr(c, "end_lineno")), default=node.lineno)
                funcs[key] = {
                    "name": node.name,
                    "mod": mod,
                    "file": rel,
                    "lineno": node.lineno,
                    "lines": e2 - node.lineno + 1,
                }

test_text = []
for root, _, files in os.walk(TESTS):
    for fn in files:
        if fn.endswith(".py"):
            test_text.append(open(os.path.join(root, fn), encoding="utf-8", errors="ignore").read())
all_tests = "\n".join(test_text)

tested_names = set()
for m in re.finditer(r"[A-Za-z_][A-Za-z0-9_]*", all_tests):
    tested_names.add(m.group(0))

untested = [(k, i) for k, i in funcs.items() if i["name"] not in tested_names]
untested.sort(key=lambda x: -x[1]["lines"])
print(f"TOPLAM_FONKSIYON: {len(funcs)}")
print(f"TEST_DISI: {len(untested)}")
print("---")
for key, info in untested:
    print(f"{info['lines']:>5}L  {key}  ({info['file']}:{info['lineno']})")
