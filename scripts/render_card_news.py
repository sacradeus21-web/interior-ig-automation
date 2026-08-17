#!/usr/bin/env python3
"""카드뉴스(텍스트 오버레이 디자인 카드) 이미지를 HTML/CSS 템플릿으로 렌더링한다.

content_bank.json의 media_kind="card_news" 항목이 가진 cards 배열(각 카드의
type/text 필드)을 받아 카드 장수만큼 PNG를 생성한다. Playwright(headless
Chromium)로 HTML을 그대로 스크린샷 떠서 이미지화하므로, 사람이 매번 손댈 필요
없이 완전 자동으로 실행 가능하다 (예약 게시 루틴에서도 그대로 재사용).

카드 타입:
  cover - 첫 장. 후킹 문구 + 큰 헤드라인
  tip   - 번호 + 소제목 + 본문 (여러 장 가능)
  outro - 마지막 장. 저장/팔로우 유도 + 브랜드
"""
import base64
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
CARD_WIDTH = 1080
CARD_HEIGHT = 1350

BRAND_NAME = "SWEET STUDIO"
BRAND_SUB = "경남인테리어"

FONT_CSS_URL = "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css"

BASE_CSS = f"""
@import url('{FONT_CSS_URL}');

* {{ margin: 0; padding: 0; box-sizing: border-box; }}

html, body {{
  width: {CARD_WIDTH}px;
  height: {CARD_HEIGHT}px;
  font-family: 'Pretendard', sans-serif;
  overflow: hidden;
  background: #F6F1EA;
}}

.card {{
  width: {CARD_WIDTH}px;
  height: {CARD_HEIGHT}px;
  position: relative;
  display: flex;
  flex-direction: column;
}}

.footer {{
  position: absolute;
  bottom: 56px;
  left: 64px;
  right: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}}

.brand {{
  display: flex;
  flex-direction: column;
  gap: 2px;
}}

.brand-name {{
  font-weight: 800;
  font-size: 22px;
  letter-spacing: 0.5px;
  color: #C1694F;
}}

.brand-sub {{
  font-weight: 500;
  font-size: 15px;
  color: #8B8378;
}}

.page-indicator {{
  font-weight: 600;
  font-size: 16px;
  color: #A69C8D;
}}
"""

COVER_TEMPLATE = """
<div class="card" style="background: linear-gradient(165deg, #F6F1EA 0%, #EDE1D3 55%, #E3CBB4 100%); align-items: center; justify-content: center; text-align: center; padding: 0 90px;">
  <div style="background: #FFFFFF; border: 1.5px solid #E3CBB4; border-radius: 999px; padding: 14px 32px; font-weight: 600; font-size: 26px; color: #C1694F; margin-bottom: 48px;">
    {hook}
  </div>
  <div style="font-weight: 800; font-size: 64px; line-height: 1.35; color: #2B2622; white-space: pre-line;">
    {headline}
  </div>
  <div style="margin-top: 44px; font-weight: 500; font-size: 24px; color: #8B7B6B;">
    {subtext}
  </div>
  <div class="footer">
    <div class="brand">
      <div class="brand-name">{brand_name}</div>
      <div class="brand-sub">{brand_sub}</div>
    </div>
    <div class="page-indicator">{page} / {total}</div>
  </div>
</div>
"""

TIP_TEMPLATE = """
<div class="card" style="background: #FFFFFF; padding: 120px 90px 0 90px;">
  <div style="font-weight: 800; font-size: 130px; color: #EDE1D3; line-height: 1; -webkit-text-stroke: 3px #C1694F;">
    {number}
  </div>
  <div style="margin-top: 24px; font-weight: 800; font-size: 46px; color: #2B2622; line-height: 1.3;">
    {title}
  </div>
  <div style="margin-top: 28px; font-weight: 400; font-size: 28px; color: #59503F; line-height: 1.6; white-space: pre-line;">
    {body}
  </div>
  <div class="footer">
    <div class="brand">
      <div class="brand-name">{brand_name}</div>
      <div class="brand-sub">{brand_sub}</div>
    </div>
    <div class="page-indicator">{page} / {total}</div>
  </div>
</div>
"""

TIP_PHOTO_TEMPLATE = """
<div class="card" style="background: #FFFFFF;">
  <img src="{photo_uri}" style="width: {width}px; height: 680px; object-fit: cover; display: block;">
  <div style="padding: 44px 90px 0 90px;">
    <div style="font-weight: 800; font-size: 56px; color: #EDE1D3; line-height: 1; -webkit-text-stroke: 2px #C1694F;">
      {number}
    </div>
    <div style="margin-top: 14px; font-weight: 800; font-size: 38px; color: #2B2622; line-height: 1.3;">
      {title}
    </div>
    <div style="margin-top: 10px; font-weight: 600; font-size: 21px; color: #C1694F;">
      {meta_line}
    </div>
    <div style="margin-top: 16px; font-weight: 400; font-size: 22px; color: #59503F; line-height: 1.5; white-space: pre-line;">
      {body}
    </div>
  </div>
  <div class="footer" style="bottom: 32px;">
    <div class="brand">
      <div class="brand-name">{brand_name}</div>
      <div class="brand-sub">{brand_sub}</div>
    </div>
    <div class="page-indicator">{page} / {total}</div>
  </div>
</div>
"""

OUTRO_TEMPLATE = """
<div class="card" style="background: #2B2622; align-items: center; justify-content: center; text-align: center; padding: 0 100px;">
  <div style="font-weight: 800; font-size: 52px; color: #F6F1EA; line-height: 1.4; white-space: pre-line;">
    {message}
  </div>
  <div style="margin-top: 40px; font-weight: 500; font-size: 24px; color: #C1694F;">
    저장하고 나중에 참고하세요 🔖
  </div>
  <div class="footer" style="bottom: 56px;">
    <div class="brand">
      <div class="brand-name" style="color: #F6F1EA;">{brand_name}</div>
      <div class="brand-sub" style="color: #A69C8D;">{brand_sub}</div>
    </div>
    <div class="page-indicator" style="color: #6B6355;">{page} / {total}</div>
  </div>
</div>
"""


def photo_data_uri(relative_path):
    photo_path = (ROOT / relative_path).resolve()
    data = base64.b64encode(photo_path.read_bytes()).decode("ascii")
    ext = photo_path.suffix.lstrip(".").lower()
    mime = "jpeg" if ext in ("jpg", "jpeg") else ext
    return f"data:image/{mime};base64,{data}"


def render_card_html(card, page, total):
    kind = card["type"]
    if kind == "cover":
        body = COVER_TEMPLATE.format(
            hook=card["hook"],
            headline=card["headline"],
            subtext=card.get("subtext", ""),
            brand_name=BRAND_NAME,
            brand_sub=BRAND_SUB,
            page=page,
            total=total,
        )
    elif kind == "tip":
        if card.get("photo"):
            body = TIP_PHOTO_TEMPLATE.format(
                photo_uri=photo_data_uri(card["photo"]),
                width=CARD_WIDTH,
                number=f"{page - 1:02d}",
                title=card["title"],
                meta_line=card.get("meta_line", ""),
                body=card["body"],
                brand_name=BRAND_NAME,
                brand_sub=BRAND_SUB,
                page=page,
                total=total,
            )
        else:
            body = TIP_TEMPLATE.format(
                number=f"{page - 1:02d}",
                title=card["title"],
                body=card["body"],
                brand_name=BRAND_NAME,
                brand_sub=BRAND_SUB,
                page=page,
                total=total,
            )
    elif kind == "outro":
        body = OUTRO_TEMPLATE.format(
            message=card["message"],
            brand_name=BRAND_NAME,
            brand_sub=BRAND_SUB,
            page=page,
            total=total,
        )
    else:
        raise ValueError(f"알 수 없는 카드 타입: {kind}")

    return f"<!doctype html><html><head><meta charset='utf-8'><style>{BASE_CSS}</style></head><body>{body}</body></html>"


def render_cards(cards, out_dir: Path, prefix: str):
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page_obj = browser.new_page(viewport={"width": CARD_WIDTH, "height": CARD_HEIGHT})
        total = len(cards)
        for i, card in enumerate(cards, start=1):
            html = render_card_html(card, i, total)
            page_obj.set_content(html, wait_until="networkidle")
            out_path = out_dir / f"{prefix}-{i:02d}.png"
            page_obj.screenshot(path=str(out_path))
            paths.append(out_path)
        browser.close()
    return paths


SAMPLE_CARDS = [
    {
        "type": "cover",
        "hook": "친환경 인테리어, 뭐부터 바꿀까?",
        "headline": "집에 자연을 들이는\n친환경 자재 3가지",
        "subtext": "오늘의 자재 p!ck ✷",
    },
    {
        "type": "tip",
        "title": "코르크",
        "body": "방음+단열까지 한번에\n바닥재·벽면 포인트로 활용하기 좋아요",
    },
    {
        "type": "tip",
        "title": "리사이클 우드",
        "body": "폐목재를 재가공해 만들어\n무늬 하나하나가 유니크해요",
    },
    {
        "type": "tip",
        "title": "라탄",
        "body": "가볍고 통풍이 잘 돼서\n수납장이나 조명갓에 딱이에요",
    },
    {
        "type": "outro",
        "message": "인테리어도 이제\n지속가능하게, 하나씩",
    },
]


if __name__ == "__main__":
    out_dir = ROOT / "scripts" / "_preview"
    paths = render_cards(SAMPLE_CARDS, out_dir, "sample")
    for p in paths:
        print(p)
