@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1/2] 파이썬 패키지 설치 중...
pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo pip 실행 실패 — Python이 설치되어 있는지 확인해주세요. https://www.python.org/downloads/
  echo 설치 시 "Add python.exe to PATH" 체크 필수!
  pause
  exit /b 1
)

echo [2/2] Playwright 크로미움 설치 중...
python -m playwright install chromium

echo.
echo 세팅 완료! config.yaml에 블로그 아이디를 입력한 뒤,
echo inbox 폴더에 사진을 넣고 Claude Code에게 "포스팅해줘"라고 말해보세요.
pause
