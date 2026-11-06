#!/usr/bin/env python3
"""Check every Python module and dashboard script, including inline JavaScript."""
from html.parser import HTMLParser
from pathlib import Path
import py_compile
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


class InlineScripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.current = None
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "script" and "src" not in values and values.get("type", "") in (
            "", "text/javascript", "application/javascript", "module"
        ):
            self.current = []

    def handle_data(self, data):
        if self.current is not None:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.current is not None:
            self.scripts.append("".join(self.current))
            self.current = None


def main():
    python_files = sorted(ROOT.glob("*.py"))
    for folder in ("scripts", "tests"):
        python_files.extend(sorted((ROOT / folder).glob("*.py")))
    for path in python_files:
        py_compile.compile(str(path), doraise=True)
    javascript = sorted((ROOT / "docs").rglob("*.js"))
    for path in javascript:
        subprocess.run(["node", "--check", str(path)], check=True)
    inline_count = 0
    for path in sorted((ROOT / "docs").rglob("*.html")):
        parser = InlineScripts()
        parser.feed(path.read_text(encoding="utf-8"))
        for i, source in enumerate(parser.scripts):
            result = subprocess.run(["node", "--check", "--input-type=module"],
                                    input=source, text=True, capture_output=True)
            if result.returncode:
                raise SystemExit(f"{path.relative_to(ROOT)} inline script {i + 1}:\n{result.stderr}")
            inline_count += 1
    print(f"Syntax OK: {len(python_files)} Python, {len(javascript)} JS, {inline_count} inline scripts")


if __name__ == "__main__":
    sys.exit(main() or 0)
