#!/usr/bin/env bash
# Create a light landing-page demo project for the agent team: brief, placeholder page,
# an objective acceptance script, a git repository and a bootstrapped ledger.
#
#   bash examples/setup-landing-demo.sh [TARGET_DIR]     (default: <protocol root>/landing-demo)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
TARGET="${1:-$(dirname "$HERE")/landing-demo}"
PROTOCOL="${AGENT_TEAM_HOME:-$(dirname "$HERE")}"
PY="$(command -v python3 || command -v python)"

[ -f "$PROTOCOL/scripts/agent_team.py" ] || {
  echo "error: protocol not found at $PROTOCOL (run install.sh first)" >&2
  exit 1
}

rm -rf "$TARGET"
mkdir -p "$TARGET"
cd "$TARGET"
TARGET="$(pwd -P)"

git init -q -b main
git config user.email "demo@example.com"
git config user.name "Demo"

cat > README.md <<'MD'
# Bát Cơm — landing page demo

Trang bán thức ăn cho chó mèo. Mục tiêu: một trang tĩnh, nhẹ, không framework, mở là chạy.

## Nội dung bắt buộc

- Thương hiệu: **Bát Cơm** — thức ăn tươi cho chó mèo.
- Ba sản phẩm, đúng giá và đúng thứ tự:

| Sản phẩm | Giá |
|---|---|
| Pate gà cho mèo | 165.000đ |
| Hạt cá hồi cho chó nhỏ | 189.000đ |
| Snack thưởng cho mèo | 149.000đ |

- Ba khu vực có `id` cố định: `menu` (sản phẩm), `why-us` (lý do chọn), `order` (đặt hàng).
- Khu `order` có một `form` với `input` họ tên, `input` số điện thoại và một `button` gửi.
- Mọi `<img>` phải có `alt` mô tả thật. Ảnh dùng placeholder ngoài (ví dụ `https://placehold.co/`)
  hoặc không dùng ảnh cũng được, miễn là không có ảnh thiếu `alt`.

## Ràng buộc kỹ thuật

- `index.html` + `styles.css`, không framework, không build step.
- `<html lang="vi">`, đúng một `<h1>`, có `<meta name="viewport">`, link tới `styles.css`.
- Mọi liên kết nội bộ `href="#..."` phải trỏ tới một `id` tồn tại.
- Không còn chữ `TODO` trong `index.html`.

## Nghiệm thu

```bash
python3 check.py      # exit 0 khi đạt hết các yêu cầu trên
```
MD

cat > index.html <<'HTML'
<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <!-- TODO: thiếu meta viewport -->
  <title>Bát Cơm</title>
  <!-- TODO: chưa link tới styles.css -->
</head>
<body>
  <header class="hero">
    <h1>Bát Cơm</h1>
    <p>Thức ăn tươi cho chó mèo.</p>
    <!-- TODO: thiếu #menu, #why-us, #order, thiếu sản phẩm, thiếu form -->
    <a class="cta" href="#order">Đặt hàng</a>
  </header>
  <img src="https://placehold.co/600x400" class="hero-img">
  <script src="app.js"></script>
</body>
</html>
HTML

cat > styles.css <<'CSS'
:root {
  --ink: #2b2118;
  --cream: #fdf6ec;
  --accent: #c2571a;
}

body {
  margin: 0;
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  color: var(--ink);
  background: var(--cream);
}
CSS

cat > check.py <<'PY'
#!/usr/bin/env python3
"""Acceptance check for the Bát Cơm landing page. Exit 0 only when README.md is satisfied."""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PRICES = {"165.000đ", "189.000đ", "149.000đ"}
REQUIRED_IDS = {"menu", "why-us", "order"}
PRICE_PATTERN = re.compile(r"^\d{1,3}(\.\d{3})+đ$")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.html_attrs: dict[str, str | None] = {}
        self.ids: set[str] = set()
        self.anchors: list[str] = []
        self.images: list[dict] = []
        self.stylesheets: list[str] = []
        self.h1_count = 0
        self.h1_text: list[str] = []
        self.meta_viewport = False
        self.forms = 0
        self.inputs = 0
        self.buttons = 0
        self.tags: list[str] = []
        self.class_text: dict[str, list[str]] = defaultdict(list)
        self.class_attrs: dict[str, list[dict]] = defaultdict(list)
        self.children: dict[str, list[str]] = defaultdict(list)
        self.placeholder_links: list[str] = []
        self._stack: list[tuple[str, set[str]]] = []
        self._buffers: list[list[str]] = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        self.tags.append(tag)
        if tag == "html":
            self.html_attrs = values
        if values.get("id"):
            self.ids.add(values["id"])
        classes = set((values.get("class") or "").split())
        if tag == "a" and (values.get("href") or "").startswith("#"):
            self.anchors.append(values["href"][1:])
        if tag == "img":
            self.images.append({"src": values.get("src", ""), "alt": values.get("alt")})
        if tag == "link" and "stylesheet" in (values.get("rel") or ""):
            self.stylesheets.append(values.get("href") or "")
        if tag == "meta" and values.get("name") == "viewport":
            self.meta_viewport = True
        if tag == "h1":
            self.h1_count += 1
        if tag == "form":
            self.forms += 1
        if tag == "input":
            self.inputs += 1
        if tag == "button":
            self.buttons += 1
        if tag in VOID:
            return
        self._stack.append((tag, classes))
        for cls in classes:
            self.class_attrs[cls].append(values)
        self._buffers.append([])

    def handle_endtag(self, tag):
        if tag in VOID or not self._stack:
            return
        open_tag, classes = self._stack.pop()
        text = "".join(self._buffers.pop()).strip()
        if open_tag != tag:
            return
        for cls in classes:
            self.class_text[cls].append(text)
        if tag == "h1":
            self.h1_text.append(text)
        for cls in classes:
            self.children[cls].append(text)

    def handle_data(self, data):
        if self._buffers:
            self._buffers[-1].append(data)


def main() -> int:
    failures: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    html_path, css_path = ROOT / "index.html", ROOT / "styles.css"
    require(html_path.is_file(), "index.html is missing")
    require(css_path.is_file(), "styles.css is missing")
    if not html_path.is_file():
        report(failures)
        return 1

    raw = html_path.read_text(encoding="utf-8")
    page = Page()
    page.feed(raw)

    require(page.html_attrs.get("lang") == "vi", '<html lang="vi"> is required')
    require(page.meta_viewport, '<meta name="viewport"> is required')
    require(any("styles.css" in href for href in page.stylesheets), "styles.css must be linked")
    require(page.h1_count == 1, f"exactly one <h1> required, found {page.h1_count}")
    require(bool("".join(page.h1_text).strip()), "<h1> must carry text")
    require("TODO" not in raw, "remove the TODO markers from index.html")

    missing = REQUIRED_IDS - page.ids
    require(not missing, f"missing required ids: {sorted(missing)}")

    dead = sorted({anchor for anchor in page.anchors if anchor not in page.ids})
    require(not dead, f"anchors without a matching id: {dead}")

    bad_alt = [image["src"] for image in page.images if not (image.get("alt") or "").strip()]
    require(not bad_alt, f"images missing alt text: {bad_alt}")

    products = page.class_attrs.get("product", [])
    require(len(products) >= 3, f"at least 3 elements with class=\"product\" required, found {len(products)}")
    prices = {text for text in page.class_text.get("price", []) if text}
    require(PRICES <= prices, f"prices missing from .price elements: {sorted(PRICES - prices)}")
    require(all(PRICE_PATTERN.match(text) for text in prices), f"prices must look like 165.000đ: {sorted(prices)}")

    require(page.forms >= 1, "the #order section needs a <form>")
    require(page.inputs >= 2, f"the order form needs at least 2 <input> fields, found {page.inputs}")
    require(page.buttons >= 1, "the order form needs a submit <button>")

    report(failures)
    return 0 if not failures else 1


def report(failures: list[str]) -> None:
    if failures:
        print(f"FAIL ({len(failures)})")
        for index, failure in enumerate(failures, start=1):
            print(f"  {index}. {failure}")
    else:
        print("PASS - landing page meets the brief")


if __name__ == "__main__":
    sys.exit(main())
PY

chmod +x check.py
git add -A
git commit -q -m "demo: brief, placeholder page and acceptance check"

"$PY" "$PROTOCOL/scripts/agent_team.py" init --repo "$TARGET" --title "build the Bát Cơm landing page" >/dev/null

echo "landing demo : $TARGET"
echo "protocol     : $PROTOCOL"
echo "ledger       : $TARGET/ledger (T-001 = build the page)"
echo
echo "baseline (must fail):"
set +e
(cd "$TARGET" && "$PY" check.py)
echo "  check.py -> exit $?"
set -e
echo
echo "next: open Claude Code in $TARGET and paste the prompt from examples/landing-prompt.md"
