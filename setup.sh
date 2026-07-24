#!/bin/bash
# 네이버 블로그 포스팅 어시스턴트 — 최초 세팅 스크립트
set -e
cd "$(dirname "$0")"

echo "📦 파이썬 패키지 설치 중..."
pip3 install -r requirements.txt

echo "🌐 Playwright 크로미움 설치 중..."
python3 -m playwright install chromium

if ! grep -q 'naver_blog_id: ".\+"' config.yaml; then
  echo ""
  echo "⚠️  config.yaml의 naver_blog_id가 비어 있습니다."
  echo "   blog.naver.com/아이디 에서 '아이디' 부분을 config.yaml에 입력해주세요."
fi

echo ""
echo "✅ 세팅 완료! inbox/에 사진을 넣고 Claude Code에게 '포스팅해줘'라고 말해보세요."
