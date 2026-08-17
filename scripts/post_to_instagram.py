#!/usr/bin/env python3
"""Instagram Graph API 자동 게시 스크립트 (캐러셀 + AI 릴스 지원).

content_bank.json에서 아직 게시하지 않은(used=false) 첫 항목을 찾아 게시한다.
- media_kind="carousel": image_files에 나열된 이미지가 images/inbox/에 전부
  (최소 2장) 준비돼 있어야 게시 대상이 된다.
- media_kind="reel": video_file이 videos/inbox/에 이미 있으면 바로 쓰고,
  없으면 video_prompt로 muapi CLI를 호출해 그 자리에서 생성한다(완전 자동).
- media_kind="card_news": cards 배열을 scripts/render_card_news.py가
  HTML/CSS 템플릿(Playwright headless Chromium)으로 렌더링해 이미지
  캐러셀로 게시한다(완전 자동, 사람이 이미지를 넣어줄 필요 없음).
게시할 콘텐츠가 없으면 에러 없이 조용히 종료한다(무인 실행 안전성).

필요 환경변수:
  IG_ACCESS_TOKEN        - Instagram 로그인 방식으로 발급한 장기(60일) 액세스 토큰
  IG_BUSINESS_ACCOUNT_ID - Instagram 비즈니스 계정의 사용자 ID (graph.instagram.com 기준)
  GITHUB_REPO            - "owner/repo" 형식 (미디어 raw URL 생성용)
  GITHUB_BRANCH          - 기본값 "main"
  MUAPI_API_KEY          - 릴스용 영상이 아직 없을 때 muapi CLI 인증에 필요
                           (muapi auth configure --api-key로 이미 로컬에 설정돼 있으면 불필요)

API 호출은 graph.instagram.com을 사용한다 (graph.facebook.com이 아님) —
Instagram 로그인 방식(Business Login for Instagram)으로 발급한 토큰은
이 호스트에서만 유효하다.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from render_card_news import render_cards

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CONTENT_BANK = ROOT / "content_bank.json"
POST_LOG = ROOT / "post_log.json"
IMAGES_INBOX_DIR = ROOT / "images" / "inbox"
IMAGES_POSTED_DIR = ROOT / "images" / "posted"
VIDEOS_INBOX_DIR = ROOT / "videos" / "inbox"
VIDEOS_POSTED_DIR = ROOT / "videos" / "posted"
CARD_NEWS_GENERATED_DIR = ROOT / "card_news" / "generated"
CARD_NEWS_POSTED_DIR = ROOT / "card_news" / "posted"
MIN_CARD_NEWS_ITEMS = 2
GRAPH_API_VERSION = "v21.0"
MIN_CAROUSEL_ITEMS = 2
VIDEO_MODEL = "kling-master"
VIDEO_DURATION = 5
VIDEO_ASPECT_RATIO = "9:16"


def load_json(path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def append_log(entry):
    log = load_json(POST_LOG, [])
    log.append(entry)
    save_json(POST_LOG, log)


def find_next_postable(bank):
    for post in bank["posts"]:
        if post.get("used"):
            continue
        kind = post.get("media_kind", "carousel")
        if kind in ("reel", "card_news"):
            return post  # 매번 게시 시점에 자동 생성하는 타입이라 항상 게시 가능
        image_files = post.get("image_files", [])
        if len(image_files) < MIN_CAROUSEL_ITEMS:
            continue
        if all((IMAGES_INBOX_DIR / f).exists() for f in image_files):
            return post
    return None


def build_caption(post):
    hashtags = " ".join(post.get("hashtags", []))
    return f"{post['caption']}\n.\n.\n.\n{hashtags}"


def graph_request(url, data=None, method="POST"):
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()
        raise RuntimeError(f"Graph API 오류 ({e.code}): {detail}") from e


def wait_until_container_ready(api_root, creation_id, access_token, timeout=60, interval=3):
    elapsed = 0
    while elapsed < timeout:
        status = graph_request(
            f"{api_root}/{creation_id}?fields=status_code&access_token={access_token}",
            method="GET",
        )
        code = status.get("status_code")
        if code == "FINISHED":
            return
        if code == "ERROR":
            raise RuntimeError(f"미디어 컨테이너 처리 실패: {status}")
        time.sleep(interval)
        elapsed += interval
    raise RuntimeError("미디어 컨테이너가 시간 내에 준비되지 않았습니다 (timeout)")


def publish_carousel_to_instagram(image_urls, caption, access_token, ig_account_id):
    api_root = f"https://graph.instagram.com/{GRAPH_API_VERSION}"
    account_base = f"{api_root}/{ig_account_id}"

    child_ids = []
    for image_url in image_urls:
        child = graph_request(
            f"{account_base}/media",
            {
                "image_url": image_url,
                "is_carousel_item": "true",
                "access_token": access_token,
            },
        )
        wait_until_container_ready(api_root, child["id"], access_token)
        child_ids.append(child["id"])

    parent = graph_request(
        f"{account_base}/media",
        {
            "media_type": "CAROUSEL",
            "children": ",".join(child_ids),
            "caption": caption,
            "access_token": access_token,
        },
    )
    wait_until_container_ready(api_root, parent["id"], access_token)

    published = graph_request(
        f"{account_base}/media_publish",
        {"creation_id": parent["id"], "access_token": access_token},
    )
    return published["id"]


def publish_reel_to_instagram(video_url, caption, access_token, ig_account_id):
    api_root = f"https://graph.instagram.com/{GRAPH_API_VERSION}"
    account_base = f"{api_root}/{ig_account_id}"

    container = graph_request(
        f"{account_base}/media",
        {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "true",
            "is_ai_generated": "true",
            "access_token": access_token,
        },
    )
    # 영상은 처리 시간이 이미지보다 훨씬 길다 (보통 30초~2분, 드물게 10분 가까이 걸리는 경우도 있음)
    wait_until_container_ready(api_root, container["id"], access_token, timeout=600, interval=15)

    published = graph_request(
        f"{account_base}/media_publish",
        {"creation_id": container["id"], "access_token": access_token},
    )
    return published["id"]


def generate_video_via_muapi(prompt, target_path):
    VIDEOS_INBOX_DIR.mkdir(parents=True, exist_ok=True)
    before = set(os.listdir(VIDEOS_INBOX_DIR))

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [
            "muapi", "video", "generate", prompt,
            "--model", VIDEO_MODEL,
            "--duration", str(VIDEO_DURATION),
            "--aspect-ratio", VIDEO_ASPECT_RATIO,
            "--download", str(VIDEOS_INBOX_DIR),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        timeout=600,
    )
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"muapi 영상 생성 실패: {stderr or stdout}")

    after = set(os.listdir(VIDEOS_INBOX_DIR))
    new_files = [f for f in (after - before) if f.lower().endswith((".mp4", ".mov"))]
    if not new_files:
        raise RuntimeError(f"muapi 생성 결과 파일을 찾을 수 없습니다. 출력: {stdout}")

    (VIDEOS_INBOX_DIR / new_files[0]).rename(target_path)


def git(*args):
    subprocess.run(["git", *args], cwd=ROOT, check=True)


def commit_and_push(message):
    git("add", "-A")
    result = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT)
    if result.returncode == 0:
        return  # 변경 없음
    git("commit", "-m", message)
    git("push")


def handle_carousel(post, github_repo, github_branch, access_token, ig_account_id):
    image_files = post["image_files"]
    image_urls = [
        f"https://raw.githubusercontent.com/{github_repo}/{github_branch}/images/inbox/{f}"
        for f in image_files
    ]
    media_id = publish_carousel_to_instagram(image_urls, build_caption(post), access_token, ig_account_id)

    IMAGES_POSTED_DIR.mkdir(parents=True, exist_ok=True)
    for f in image_files:
        (IMAGES_INBOX_DIR / f).rename(IMAGES_POSTED_DIR / f)

    return media_id, {"image_count": len(image_files)}


def handle_reel(post, github_repo, github_branch, access_token, ig_account_id):
    video_path = VIDEOS_INBOX_DIR / post["video_file"]

    if not video_path.exists():
        print(f"영상이 아직 없어 muapi로 생성합니다: {post['id']}")
        generate_video_via_muapi(post["video_prompt"], video_path)
        # Graph API가 fetch할 수 있도록, 발행 시도 전에 먼저 공개 저장소에 반영
        commit_and_push(f"content: {post['id']} 영상 생성")

    video_url = f"https://raw.githubusercontent.com/{github_repo}/{github_branch}/videos/inbox/{post['video_file']}"
    media_id = publish_reel_to_instagram(video_url, build_caption(post), access_token, ig_account_id)

    VIDEOS_POSTED_DIR.mkdir(parents=True, exist_ok=True)
    video_path.rename(VIDEOS_POSTED_DIR / post["video_file"])

    return media_id, {"video_file": post["video_file"]}


def handle_card_news(post, github_repo, github_branch, access_token, ig_account_id):
    cards = post["cards"]
    if len(cards) < MIN_CARD_NEWS_ITEMS:
        raise RuntimeError(f"카드뉴스는 최소 {MIN_CARD_NEWS_ITEMS}장이 필요합니다 (현재 {len(cards)}장)")

    gen_dir = CARD_NEWS_GENERATED_DIR / post["id"]
    image_paths = render_cards(cards, gen_dir, post["id"])

    # Graph API가 fetch할 수 있도록, 발행 시도 전에 먼저 공개 저장소에 반영
    commit_and_push(f"content: {post['id']} 카드뉴스 이미지 생성")

    image_urls = [
        f"https://raw.githubusercontent.com/{github_repo}/{github_branch}/card_news/generated/{post['id']}/{p.name}"
        for p in image_paths
    ]
    media_id = publish_carousel_to_instagram(image_urls, build_caption(post), access_token, ig_account_id)

    CARD_NEWS_POSTED_DIR.mkdir(parents=True, exist_ok=True)
    posted_dir = CARD_NEWS_POSTED_DIR / post["id"]
    gen_dir.rename(posted_dir)

    return media_id, {"card_count": len(image_paths)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="실제 게시 없이 로직만 확인")
    args = parser.parse_args()

    bank = load_json(CONTENT_BANK, {"posts": []})
    post = find_next_postable(bank)

    if post is None:
        print(f"게시할 콘텐츠가 없습니다: 캐러셀용 이미지(최소 {MIN_CAROUSEL_ITEMS}장)가 다 준비된 항목도, 릴스 항목도 없어요. 건너뜁니다.")
        append_log({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "skipped",
            "reason": "no postable content",
        })
        commit_and_push("chore: post_log 업데이트 (게시할 콘텐츠 없음)")
        return 0

    kind = post.get("media_kind", "carousel")
    caption = build_caption(post)

    if args.dry_run:
        print(f"[dry-run] 게시 예정 콘텐츠: {post['id']} - {post['topic']} ({kind})")
        print(f"[dry-run] 캡션:\n{caption}")
        return 0

    access_token = os.environ["IG_ACCESS_TOKEN"]
    ig_account_id = os.environ["IG_BUSINESS_ACCOUNT_ID"]
    github_repo = os.environ["GITHUB_REPO"]
    github_branch = os.environ.get("GITHUB_BRANCH", "main")

    try:
        if kind == "reel":
            media_id, extra = handle_reel(post, github_repo, github_branch, access_token, ig_account_id)
        elif kind == "card_news":
            media_id, extra = handle_card_news(post, github_repo, github_branch, access_token, ig_account_id)
        else:
            media_id, extra = handle_carousel(post, github_repo, github_branch, access_token, ig_account_id)
    except Exception as e:
        print(f"게시 실패: {e}", file=sys.stderr)
        append_log({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "failed",
            "post_id": post["id"],
            "media_kind": kind,
            "error": str(e),
        })
        commit_and_push(f"chore: 게시 실패 로그 ({post['id']})")
        return 1

    post["used"] = True
    post["posted_at"] = datetime.now(timezone.utc).isoformat()
    save_json(CONTENT_BANK, bank)

    append_log({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "posted",
        "post_id": post["id"],
        "media_kind": kind,
        "ig_media_id": media_id,
        **extra,
    })

    commit_and_push(f"post: {post['id']} 게시 완료 ({kind})")
    print(f"게시 완료: {post['id']} (media_id={media_id}, {kind})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
