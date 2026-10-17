"""리포트(Markdown)를 A4 PDF로 만든다.

사용법: .venv/bin/python src/make_pdf.py   (markdown 라이브러리, Google Chrome 필요)
입력: outputs/report/report.md
출력: outputs/report/report.pdf
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "outputs" / "report" / "report.md"
OUT = ROOT / "outputs" / "report" / "report.pdf"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

CSS = """
@page { size: A4; margin: 16mm 15mm; }
body { font-family: "Apple SD Gothic Neo", system-ui, sans-serif; font-size: 10pt; line-height: 1.6;
       color: #0b0b0b; background: #fff; }
h1 { font-size: 20pt; margin: 0 0 2pt; }
h3 { color: #52514e; font-weight: 500; margin-top: 0; }
h2 { font-size: 14pt; border-bottom: 1px solid #e1e0d9; padding-bottom: 3pt; margin-top: 18pt; }
h1 + h3 { font-size: 12pt; }
blockquote { color: #52514e; border-left: 3px solid #c3c2b7; margin: 6pt 0; padding: 2pt 10pt; }
table { border-collapse: collapse; width: 100%; font-size: 8.5pt; margin: 6pt 0; }
th, td { border-bottom: 1px solid #e1e0d9; padding: 4pt 6pt; text-align: left; vertical-align: top; }
th { background: #f6f6f4; }
td:first-child, th:first-child { min-width: 4em; }  /* 짧은 첫 열(운영자·유저 등)이 한 글자씩 쪼개지지 않게 */
img { max-width: 100%; display: block; margin: 8pt auto; }
code { font-size: 9pt; background: #f3f3f1; padding: 0 3pt; border-radius: 3px; }
hr { border: 0; border-top: 1px solid #e1e0d9; margin: 14pt 0; }
table, img, blockquote { break-inside: avoid; }
h2, h3 { break-after: avoid; }
li { margin: 1pt 0; }
"""


def normalize_lists(text):
    """markdown 라이브러리가 목록을 인식하도록 맞춘다.
    1) 하위 목록 들여쓰기(2~3칸) → 4칸  2) 일반 문장 바로 다음 줄에서 시작하는 목록 앞에 빈 줄 추가"""
    text = re.sub(r"^ {2,3}(?=[-*] |\d+\. )", "    ", text, flags=re.M)
    item = re.compile(r"^\s*([-*] |\d+\. )")
    out = []
    for line in text.split("\n"):
        prev = out[-1] if out else ""
        if item.match(line) and prev.strip() and not item.match(prev) and not prev.startswith(" "):
            out.append("")
        out.append(line)
    return "\n".join(out)


def main():
    if not Path(CHROME).exists():
        sys.exit("Google Chrome이 없습니다: " + CHROME)
    body = markdown.markdown(normalize_lists(SRC.read_text(encoding="utf-8")),
                             extensions=["tables", "fenced_code", "sane_lists"])
    # base: 리포트 폴더 기준으로 차트 이미지(../charts/...) 경로를 찾게 함
    html = (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            f'<base href="{SRC.parent.as_uri()}/"><style>{CSS}</style></head><body>{body}</body></html>')
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "report.html"
        page.write_text(html, encoding="utf-8")
        result = subprocess.run([CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                                 "--allow-file-access-from-files", f"--print-to-pdf={OUT}", page.as_uri()],
                                capture_output=True, text=True, timeout=120)
    if not OUT.exists():
        sys.exit(f"PDF 생성 실패:\n{result.stderr[-1000:]}")
    print(f"저장: {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f}KB)")


if __name__ == "__main__":
    main()
