"""사용법: python3 publish.py drafts/20260714_153000 [--schedule "YYYY-MM-DD HH:MM"]
post.json을 읽어 네이버 에디터에 자동 입력합니다. --schedule을 주면 예약 발행."""
import json
import sys
from pathlib import Path

import yaml

from publisher import publish_auto, publish_clipboard

BASE = Path(__file__).parent


def main():
    schedule = None
    if "--schedule" in sys.argv:
        i = sys.argv.index("--schedule")
        schedule = sys.argv[i + 1]
        del sys.argv[i:i + 2]

    if len(sys.argv) < 2:
        # 인자 없으면 가장 최근 draft 사용
        drafts = sorted((BASE / "drafts").glob("*/post.json"))
        if not drafts:
            print("발행할 초안이 없습니다. drafts/<폴더>/post.json 필요")
            sys.exit(1)
        draft_dir = drafts[-1].parent
        print(f"최근 초안 사용: {draft_dir.name}")
    else:
        draft_dir = Path(sys.argv[1])
        if not draft_dir.is_absolute():
            draft_dir = BASE / draft_dir

    post = json.loads((draft_dir / "post.json").read_text(encoding="utf-8"))

    # 이미지/동영상 경로를 절대경로로 정규화 (draft 폴더 기준 상대경로도 보정)
    def _normalize(paths):
        fixed = []
        for p in paths:
            pp = Path(p) if Path(p).is_absolute() else BASE / p
            fixed.append(str(pp if pp.exists() else draft_dir / Path(p).name))
        return fixed

    post["images"] = _normalize(post.get("images", []))
    post["videos"] = _normalize(post.get("videos", []))

    config = yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))
    if not config.get("naver_blog_id"):
        print("config.yaml에 naver_blog_id를 먼저 입력해주세요.")
        sys.exit(1)

    if config.get("publish_mode") == "clipboard":
        publish_clipboard(post, config)
    else:
        publish_auto(post, config, schedule=schedule)


if __name__ == "__main__":
    main()
