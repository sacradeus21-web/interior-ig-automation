#!/usr/bin/env python3
"""릴스 게시가 IN_PROGRESS에서 멈추는 문제를 진단하기 위한 1회성 스크립트.

reel-001.mp4를 (a) media_type=REELS 컨테이너와 (b) media_type=VIDEO(피드용) 컨테이너
양쪽으로 각각 생성해보고 status_code를 폴링해서, Reels 처리 특유의 문제인지
아니면 영상 자체/일반 영상 인입 파이프라인의 문제인지 구분한다.

실제 media_publish는 호출하지 않는다 (컨테이너 생성 + 상태 폴링까지만) — 안전한 진단용.
토큰 값 자체는 어떤 로그에도 출력하지 않는다.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
GRAPH_API_VERSION = "v21.0"


def load_env(path):
    env = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def graph_request(url, data=None, method="POST"):
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()
        raise RuntimeError(f"Graph API 오류 ({e.code}): {detail}") from e


def redact(url, token):
    return url.replace(token, "***")


def poll(api_root, creation_id, token, label, max_minutes=8, interval=15):
    print(f"[{label}] container id = {creation_id}, 폴링 시작 (최대 {max_minutes}분)")
    elapsed = 0
    timeout = max_minutes * 60
    while elapsed < timeout:
        status = graph_request(
            f"{api_root}/{creation_id}?fields=status_code&access_token={token}",
            method="GET",
        )
        code = status.get("status_code")
        print(f"[{label}] t+{elapsed:>4}s status_code={code}")
        if code in ("FINISHED", "ERROR", "EXPIRED"):
            return code, status
        time.sleep(interval)
        elapsed += interval
    return "TIMEOUT", None


def main():
    env = load_env(ENV_PATH)
    token = env["IG_ACCESS_TOKEN"]
    ig_account_id = env["IG_BUSINESS_ACCOUNT_ID"]
    github_repo = env.get("GITHUB_REPO", "sacradeus21-web/interior-ig-automation")
    github_branch = env.get("GITHUB_BRANCH", "main")

    video_url = f"https://raw.githubusercontent.com/{github_repo}/{github_branch}/videos/inbox/reel-001.mp4"
    print(f"video_url = {video_url}")

    api_root = f"https://graph.instagram.com/{GRAPH_API_VERSION}"
    account_base = f"{api_root}/{ig_account_id}"

    me = graph_request(f"{api_root}/me?fields=id,username,account_type&access_token={token}", method="GET")
    print(f"token check OK: {me}")

    mode = sys.argv[1] if len(sys.argv) > 1 else "video"

    if mode == "video":
        print("\n=== 진단 (b): media_type=VIDEO (일반 피드 영상)로 생성 ===")
        container = graph_request(
            f"{account_base}/media",
            {
                "media_type": "VIDEO",
                "video_url": video_url,
                "access_token": token,
            },
        )
        code, status = poll(api_root, container["id"], token, "VIDEO")
        print(f"\n최종 결과 (VIDEO): {code} {status or ''}")
        print(f"컨테이너 id 기록해둘 것: {container['id']} (문제 없으면 나중에 media_publish로 직접 발행 가능, 안하면 자동 만료됨)")

    elif mode == "reel":
        print("\n=== 진단 (a): media_type=REELS로 재생성 (기존 것과 별개의 새 컨테이너) ===")
        container = graph_request(
            f"{account_base}/media",
            {
                "media_type": "REELS",
                "video_url": video_url,
                "share_to_feed": "true",
                "is_ai_generated": "true",
                "access_token": token,
            },
        )
        code, status = poll(api_root, container["id"], token, "REELS")
        print(f"\n최종 결과 (REELS): {code} {status or ''}")

    else:
        print("사용법: python diagnose_reel_stuck.py [video|reel]")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
