#!/usr/bin/env python3
"""Instagram Graph API 자동 게시 스크립트.

content_bank.json에서 아직 게시하지 않았고(used=false) images/inbox/에
이미지 파일이 준비된 첫 항목을 찾아 인스타그램에 게시한다.
게시할 콘텐츠가 없으면 에러 없이 조용히 종료한다(무인 실행 안전성).

필요 환경변수:
  IG_ACCESS_TOKEN       - Meta 장기 액세스 토큰
  IG_BUSINESS_ACCOUNT_ID - Instagram 비즈니스 계정 ID
  GITHUB_REPO           - "owner/repo" 형식 (이미지 raw URL 생성용)
  GITHUB_BRANCH         - 기본값 "main"
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CONTENT_BANK = ROOT / "content_bank.json"
POST_LOG = ROOT / "post_log.json"
INBOX_DIR = ROOT / "images" / "inbox"
POSTED_DIR = ROOT / "images" / "posted"
GRAPH_API_VERSION = "v21.0"


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
        image_path = INBOX_DIR / post["image_file"]
        if image_path.exists():
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


def publish_to_instagram(image_url, caption, access_token, ig_account_id):
    base = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{ig_account_id}"

    container = graph_request(
        f"{base}/media",
        {"image_url": image_url, "caption": caption, "access_token": access_token},
    )
    creation_id = container["id"]

    published = graph_request(
        f"{base}/media_publish",
        {"creation_id": creation_id, "access_token": access_token},
    )
    return published["id"]


def git(*args):
    subprocess.run(["git", *args], cwd=ROOT, check=True)


def commit_and_push(message):
    git("add", "content_bank.json", "post_log.json", "images/")
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=ROOT
    )
    if result.returncode == 0:
        return  # 변경 없음
    git("commit", "-m", message)
    git("push")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="실제 게시 없이 로직만 확인")
    args = parser.parse_args()

    bank = load_json(CONTENT_BANK, {"posts": []})
    post = find_next_postable(bank)

    if post is None:
        print("게시할 콘텐츠가 없습니다: images/inbox/에 대기 중인 이미지가 없어요. 건너뜁니다.")
        append_log({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "skipped",
            "reason": "no image ready in images/inbox/",
        })
        commit_and_push("chore: post_log 업데이트 (게시할 이미지 없음)")
        return 0

    caption = build_caption(post)

    if args.dry_run:
        print(f"[dry-run] 게시 예정 콘텐츠: {post['id']} - {post['topic']}")
        print(f"[dry-run] 캡션:\n{caption}")
        return 0

    access_token = os.environ["IG_ACCESS_TOKEN"]
    ig_account_id = os.environ["IG_BUSINESS_ACCOUNT_ID"]
    github_repo = os.environ["GITHUB_REPO"]
    github_branch = os.environ.get("GITHUB_BRANCH", "main")

    image_url = (
        f"https://raw.githubusercontent.com/{github_repo}/{github_branch}"
        f"/images/inbox/{post['image_file']}"
    )

    try:
        media_id = publish_to_instagram(image_url, caption, access_token, ig_account_id)
    except Exception as e:
        print(f"게시 실패: {e}", file=sys.stderr)
        append_log({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "failed",
            "post_id": post["id"],
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
        "ig_media_id": media_id,
    })

    POSTED_DIR.mkdir(parents=True, exist_ok=True)
    (INBOX_DIR / post["image_file"]).rename(POSTED_DIR / post["image_file"])

    commit_and_push(f"post: {post['id']} 게시 완료")
    print(f"게시 완료: {post['id']} (media_id={media_id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
