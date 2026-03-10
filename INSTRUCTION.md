# BTC 트레이딩 앱 — 설치 및 실행 가이드

## 사전 요구사항

| 항목 | 버전 | 설치 여부 |
|------|------|-----------|
| Anaconda (Python 3.12) | 최신 | ✅ 설치됨 |
| Node.js (conda) | 최신 | ✅ 설치됨 |

---

## 1. 최초 설치 (처음 한 번만)

### 1-1. 백엔드 Python 패키지 설치

```bash
C:\Users\etri\anaconda3\Scripts\pip.exe install fastapi uvicorn[standard] pyupbit pandas-ta aiosqlite python-dotenv websockets httpx
```

### 1-2. 프론트엔드 Node 패키지 설치

```bash
# 프로젝트 루트(Trading/)에서 실행
set PATH=C:\Users\etri\anaconda3;%PATH%
cd frontend
npm install
cd ..
```

---

## 2. 업비트 API 키 설정 (실거래 시 필요)

1. [업비트 Open API](https://upbit.com/service_center/open_api_guide) 에서 API 키 발급
2. 프로젝트 루트에 `.env` 파일 생성:

```
UPBIT_ACCESS_KEY=발급받은_액세스키
UPBIT_SECRET_KEY=발급받은_시크릿키
```

> **모의투자만 사용할 경우** `.env` 파일 없이도 정상 동작합니다.

---

## 3. 서버 실행

### 방법 A — Claude Code에서 자동 실행 (권장)

Claude Code 터미널에서:
```
/preview Backend (FastAPI)
/preview Frontend (Vite)
```

또는 Claude에게 "서버 시작해줘"라고 요청하면 자동으로 시작됩니다.

---

### 방법 B — 수동 실행

**터미널 1 — 백엔드 (포트 8000)**
```bash
cd C:\Users\etri\Desktop\Coding\Trading
C:\Users\etri\anaconda3\python.exe start_backend.py
```

**터미널 2 — 프론트엔드 (포트 5173)**
```bash
cd C:\Users\etri\Desktop\Coding\Trading
set PATH=C:\Users\etri\anaconda3;%PATH%
C:\Users\etri\anaconda3\node.exe frontend\node_modules\vite\bin\vite.js frontend --port 5173 --config frontend\vite.config.js
```

---

### 방법 C — 배치 파일로 한 번에 실행

`start_all.bat` 더블클릭:
```
C:\Users\etri\Desktop\Coding\Trading\start_all.bat
```

---

## 4. 앱 접속

백엔드와 프론트엔드가 모두 실행된 후:

| 서비스 | 주소 |
|--------|------|
| **트레이딩 앱** | http://localhost:5173 |
| **백엔드 API 문서** | http://localhost:8000/docs |

---

## 5. 기능 사용 방법

### 📈 차트 탭
- 타임프레임 버튼(1m / 3m / 5m / 15m / 1h / 1d)으로 캔들 주기 변경
- **MA** 버튼: 이동평균선 (5 / 20 / 60) 표시/숨기기
- **BB** 버튼: 볼린저밴드 표시/숨기기

### 🤖 자동매매 탭
1. **전략 선택**: RSI / MACD / 볼린저밴드 / MA 크로스
2. **파라미터** 설정 (기간, 과매수/과매도 기준 등)
3. **모드 선택**: 모의투자(무료) 또는 실거래(API 키 필요)
4. **손절/익절 %** 및 **투자 비율** 설정
5. `▶ 모의투자 시작` 버튼 클릭
6. 실행 중 상태: 포지션, 현재 손익, 시그널 로그 실시간 확인

### 📊 백테스팅 탭
1. 전략 / 타임프레임 / 기간(일) 설정
2. `▶ 백테스트 실행` 클릭
3. 결과 확인: 총 수익률, 승률, MDD, Sharpe Ratio, 자산 곡선

### 💼 포트폴리오 탭
- 모의투자 KRW / BTC 잔고 확인
- 전체 거래 내역 조회

---

## 6. 프로젝트 구조

```
Trading/
├── .env                    # API 키 (직접 생성)
├── .env.example            # API 키 예시
├── start_backend.py        # 백엔드 실행 진입점
├── start_frontend.bat      # 프론트엔드 실행 배치
├── .claude/launch.json     # Claude Code 서버 설정
│
├── backend/
│   ├── main.py             # FastAPI 앱
│   ├── requirements.txt    # Python 패키지 목록
│   ├── core/
│   │   ├── upbit_client.py # Upbit API 연동
│   │   ├── strategies.py   # 매매 전략 (RSI, MACD, BB, MA)
│   │   ├── bot.py          # 자동매매 봇 엔진
│   │   └── backtest.py     # 백테스팅 엔진
│   ├── api/
│   │   ├── routes.py       # REST API 엔드포인트
│   │   └── ws_handler.py   # WebSocket 핸들러
│   └── db/
│       └── database.py     # SQLite DB 초기화
│
└── frontend/
    ├── src/
    │   ├── App.jsx
    │   ├── components/
    │   │   ├── Chart.jsx       # 실시간 캔들 차트
    │   │   ├── Ticker.jsx      # 현재가 표시
    │   │   ├── BotControl.jsx  # 봇 제어 UI
    │   │   ├── Portfolio.jsx   # 포트폴리오
    │   │   └── Backtest.jsx    # 백테스팅 UI
    │   └── services/
    │       ├── api.js          # REST 호출
    │       └── websocket.js    # WebSocket 클라이언트
    └── package.json
```

---

## 7. 문제 해결

| 증상 | 해결 방법 |
|------|-----------|
| 백엔드 시작 안 됨 | `pip install` 재실행 후 다시 시도 |
| 차트에 데이터 없음 | 인터넷 연결 확인, 업비트 서버 상태 확인 |
| 실거래 주문 실패 | `.env` 파일의 API 키 확인, 업비트 IP 허용 설정 확인 |
| 프론트 빈 화면 | 백엔드(8000)가 먼저 실행됐는지 확인 |
| npm not found | `set PATH=C:\Users\etri\anaconda3;%PATH%` 실행 후 재시도 |

---

## 8. 주의사항

> ⚠️ **실거래 모드**는 실제 자산을 사용합니다. 반드시 **모의투자 모드**로 충분히 테스트한 후 사용하세요.

> ⚠️ 자동매매는 시장 상황에 따라 손실이 발생할 수 있습니다. 투자 결과에 대한 책임은 사용자 본인에게 있습니다.
