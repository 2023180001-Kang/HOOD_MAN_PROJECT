# HOOD_MAN_PROJECT

Python과 pico2d로 구현한 2D 횡스크롤 액션 게임입니다. 개발 명세는 [PRD.md](PRD.md), 단계별 기록은 [DEVELOPMENT.md](DEVELOPMENT.md), 검증 결과는 [TESTING.md](TESTING.md)를 참고하세요.

## 실행 환경

- Windows 64비트
- 확인한 버전: Python 3.13.15, pico2d 1.5.1
- 1280×720 창, 60 FPS 렌더링 목표, 120Hz 고정 물리 갱신

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
| Space | 점프, 공중에서 다시 누르면 이단 점프 |
| R | 플레이·피격·사망 중 처음부터 다시 시작 |
| 창 닫기 | 종료 |

적은 맵 양 끝에서 1·3·5·7초에 총 4명 등장합니다. 주인공 HP는 500이고, 적의 유효 공격마다 20씩 감소합니다. HP가 0이면 쓰러지면서 등장한 적들을 바깥쪽으로 밀어냅니다. 주인공 공격 기능은 없습니다.

- 걷기는 300px/s, 달리기는 720px/s입니다. 방향키 해제·방향 전환·Shift 해제에 강한 제동을 적용하여 미끄러짐을 줄였습니다.
- 달리면서 두 번째 점프할 때 Shift와 방향키를 유지하면 더 높고 멀리 뛰어넘습니다.
- 좌우 동시 입력은 중립으로 처리합니다. Space와 R을 길게 눌러도 동작이 반복되지 않습니다.
- 피격 중에는 이동·점프를 잠시 제한합니다. 점프 중 피격되어도 중력은 계속 적용됩니다.
- 여러 적의 공격은 각각 20 피해를 줍니다. 2명이 동시에 맞히면 40, 4명이면 80이 감소하며 피격 모션 중에도 다른 공격의 피해가 적용됩니다. 같은 적의 같은 공격은 한 번만 피해를 줍니다.
- 창 포커스를 잃으면 눌린 키를 해제하여 이동이 고정되는 현상을 방지합니다.
- R은 HP·위치·적·생성 일정·카메라·효과·입력을 초기화합니다.

## 개발 검증

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe tools/prepare_assets.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe main.py --smoke-test 120
.\.venv\Scripts\python.exe tools/check_render.py
.\.venv\Scripts\python.exe tools/check_runtime.py
```

원본 PNG를 보존하며 `assets/frames.json`에 프레임별 클립 좌표를 생성합니다. 생성된 파일이 저장소에 포함되어 있어 일반 실행에는 Pillow가 필요하지 않습니다. 스모크 테스트는 실제 pico2d 창에서 지정한 프레임을 렌더링하고 정상 종료합니다.

`check_render.py`는 주요 상태의 실제 렌더링 화면을 `artifacts/`에 저장합니다. `check_runtime.py`는 SDL 키 이벤트·HP바 픽셀·창 포커스·재시작·정상 종료를 검사하고 적 4명 상황의 FPS를 출력합니다.

## 코드 구성과 조정

| 파일 | 역할 |
| --- | --- |
| `main.py`, `game.py` | 캔버스·SDL 입력·게임 루프·렌더링·종료 |
| `world.py` | 그래픽과 독립된 고정 시간 시뮬레이션·사망 이벤트·재시작 |
| `player.py`, `controls.py`, `physics.py` | 이동·점프·피격·사망 상태와 입력·물리 |
| `enemy.py`, `spawn_manager.py`, `collision.py` | 적 추적·공격·넉백·생성 일정·충돌 |
| `assets.py`, `animation.py` | 이미지·Windows 기본 맑은 고딕 로딩, 프레임 재생 |
| `stage.py`, `camera.py`, `ui.py` | 배경·카메라·화면 고정 HP UI |
| `config.py` | 이동 속도·중력·피해·넉백·스폰·애니메이션 조정값 |

원본 주인공·적·HP·배경 PNG는 프로젝트 루트에 유지합니다. 리소스를 교체하면 개발 의존성을 설치한 후 `tools/prepare_assets.py`로 프레임 정보를 다시 생성합니다. 스프라이트 시트는 2048×1536, 8열×6행, 오른쪽을 보는 원본을 기준으로 합니다. 글꼴이 없는 환경에서도 게임과 이미지 HP바는 동작하며 텍스트만 생략됩니다.
