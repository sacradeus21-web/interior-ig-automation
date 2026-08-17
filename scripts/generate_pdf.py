#!/usr/bin/env python3
"""댓글 → DM 자동 발송용 PDF 자료를 HTML/CSS 템플릿으로 생성한다.

카드뉴스(render_card_news.py)와 동일한 브랜드 톤(크림/버건디, Pretendard)을
쓰지만, 출력은 이미지가 아니라 A4 PDF 한 장이다. Playwright의 page.pdf()를
사용한다.
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
BRAND_NAME = "SWEET STUDIO"
BRAND_SUB = "경남인테리어"
FONT_CSS_URL = "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css"


def build_html(title, intro, items, outro):
    rows = ""
    for i, item in enumerate(items, start=1):
        rows += f"""
        <div class="item">
          <div class="item-number">{i:02d}</div>
          <div class="item-body">
            <div class="item-title">{item['title']}</div>
            <div class="item-meta">{item.get('meta_line', '')}</div>
            <div class="item-desc">{item['body']}</div>
          </div>
        </div>
        """

    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
@import url('{FONT_CSS_URL}');
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: 'Pretendard', sans-serif;
  background: #F6F1EA;
  color: #2B2622;
  padding: 56px 64px;
}}
.brand-name {{ font-weight: 800; font-size: 20px; color: #7A2333; letter-spacing: 0.5px; }}
.brand-sub {{ font-weight: 500; font-size: 13px; color: #8B8378; margin-top: 2px; }}
.title {{ font-weight: 800; font-size: 34px; line-height: 1.3; margin-top: 36px; }}
.intro {{ font-weight: 400; font-size: 15px; color: #59503F; line-height: 1.6; margin-top: 14px; white-space: pre-line; }}
.item {{
  display: flex; gap: 20px;
  margin-top: 30px; padding-bottom: 24px;
  border-bottom: 1px solid #E3CBB4;
}}
.item-number {{ font-weight: 800; font-size: 30px; color: #EDE1D3; -webkit-text-stroke: 1.5px #7A2333; min-width: 44px; }}
.item-title {{ font-weight: 800; font-size: 19px; }}
.item-meta {{ font-weight: 600; font-size: 13px; color: #7A2333; margin-top: 4px; }}
.item-desc {{ font-weight: 400; font-size: 14px; color: #59503F; line-height: 1.5; margin-top: 6px; white-space: pre-line; }}
.outro {{ margin-top: 40px; font-weight: 500; font-size: 13px; color: #8B7B6B; line-height: 1.6; white-space: pre-line; }}
</style></head>
<body>
  <div class="brand-name">{BRAND_NAME}</div>
  <div class="brand-sub">{BRAND_SUB}</div>
  <div class="title">{title}</div>
  <div class="intro">{intro}</div>
  {rows}
  <div class="outro">{outro}</div>
</body></html>"""


def render_pdf(title, intro, items, outro, out_path: Path):
    html = build_html(title, intro, items, outro)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html, wait_until="networkidle")
        page.pdf(path=str(out_path), format="A4", print_background=True,
                 margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        browser.close()
    return out_path


LIGHTING_PICKS = [
    {
        "title": "스피아노 올리스 스윙 플로어 장스탠드",
        "meta_line": "오늘의집 · ⭐4.8 (8,163리뷰)",
        "body": "거실 소파 옆에 하나면 은은한 라운지 무드 완성",
    },
    {
        "title": "레나에너지 키노 LED 머쉬룸 무드등",
        "meta_line": "오늘의집 · ⭐4.8 (4,897리뷰)",
        "body": "침대 협탁 위에 올리면 은은한 수면 조명으로 딱",
    },
    {
        "title": "이케아 포르소 작업등 단스탠드",
        "meta_line": "이케아 · ⭐4.9 (543리뷰)",
        "body": "각도 자유자재로 꺾이는 작업·독서용 스탠드",
    },
    {
        "title": "이케아 파도 탁상스탠드",
        "meta_line": "이케아 · ⭐4.6 (963리뷰)",
        "body": "동그란 유백색 갓이 은은하게 퍼지는 빛",
    },
]


if __name__ == "__main__":
    out = ROOT / "assets" / "pdf" / "lighting-picks.pdf"
    render_pdf(
        title="진짜 인기 많은\n스탠드 조명 4가지",
        intro="리뷰 많고 평점 높은 것만 골라서 정리했어요.\n(리뷰 수·가격은 시기에 따라 달라질 수 있어요, 구매 전 판매처에서 최신 정보 확인하세요)",
        items=LIGHTING_PICKS,
        outro="더 궁금한 점은 댓글이나 DM으로 편하게 물어보세요!\n@sweet.studio_official",
        out_path=out,
    )
    print(out)
