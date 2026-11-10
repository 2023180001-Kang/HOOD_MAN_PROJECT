# HOOD_MAN_PROJECT

Python과 pico2d로 만드는 2D 횡스크롤 액션 게임입니다. 개발 명세는 [PRD.md](PRD.md), 단계별 기록은 [DEVELOPMENT.md](DEVELOPMENT.md)를 참고하세요.

## 실행 환경

- Windows 64비트
- 확인한 버전: Python 3.13.15, pico2d 1.5.1

## 설치와 실행 (PowerShell)

프로젝트 폴더에서 실행합니다. Python이 없다면 Python 3.13 64비트를 먼저 설치합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

리소스는 소스 파일 위치를 기준으로 읽으므로 다른 작업 폴더에서 `main.py`의 전체 경로로 실행해도 됩니다.

## 조작

| 입력 | 동작 |
| --- | --- |
| 좌우 방향키 | 걷기 |
| 왼쪽/오른쪽 Shift + 방향키 | 가속하여 달리기 |
| 창 닫기 | 종료 |

## 개발 검증

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe tools/prepare_assets.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe main.py --smoke-test 120
```

원본 PNG를 보존하며 `assets/frames.json`에 프레임별 클립 좌표를 생성합니다. 생성된 파일이 저장소에 포함되어 있어 일반 실행에는 Pillow가 필요하지 않습니다. 스모크 테스트는 실제 pico2d 창에서 지정한 프레임을 렌더링하고 정상 종료합니다.
