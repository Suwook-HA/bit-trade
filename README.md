# ₿ BTC 트레이딩 앱

업비트 API 기반 비트코인 자동매매 웹 애플리케이션입니다.
실시간 차트, 자동매매 봇, 백테스팅, 포트폴리오 관리 기능을 제공합니다.

---

## 기술 스택

| 구분 | 기술 |
|------|------|
| Backend | Python 3.12 · FastAPI · uvicorn · pyupbit |
| Frontend | React · Vite · Tailwind CSS · lightweight-charts |
| Database | SQLite (aiosqlite) |
| 거래소 | 업비트 (Upbit) |

---

## 주요 기능

### 📈 실시간 차트
- 1m / 3m / 5m / 15m / 1h / 1d 타임프레임
- 이동평균선 (MA 5/20/60) · 볼린저밴드 오버레이
- WebSocket 실시간 현재가 업데이트

### 🤖 자동매매 봇
- **전략**: RSI 과매수/과매도 · MACD · 볼린저밴드 · MA 크로스
- **모드**: 모의투자(페이퍼) / 실거래
- 손절(Stop Loss) · 익절(Take Profit) 설정
- 실행 주기 독립 설정 (10초 ~ 1시간)
- 자동 전략 추천 & 파라미터 자동 재조정
- 실시간 포지션 · 손익 · 시그널 로그

### 📊 백테스팅
- 전략별 과거 데이터 시뮬레이션
- 총 수익률 · 승률 · MDD · Sharpe Ratio · 자산 곡선

### 💼 포트폴리오
- 모의/실거래 KRW · BTC 잔고 현황
- 전체 거래 내역 조회

---

## 설치 및 실행

### 사전 요구사항
- [Anaconda](https://www.anaconda.com/) (Python 3.12 포함)
- Node.js (Anaconda에 포함되어 있거나 별도 설치)

### 1. 패키지 설치 (최초 1회)

**백엔드**
```bash
pip install fastapi "uvicorn[standard]" pyupbit pandas-ta aiosqlite python-dotenv websockets httpx
```

**프론트엔드**
```bash
cd frontend
npm install
```

### 2. 업비트 API 키 설정 (실거래 시)

프로젝트 루트에 `.env` 파일 생성:
```
UPBIT_ACCESS_KEY=발급받은_액세스키
UPBIT_SECRET_KEY=발급받은_시크릿키
```
> 모의투자만 사용할 경우 `.env` 없이도 동작합니다.

### 3. 서버 실행

**터미널 1 — 백엔드 (포트 8000)**
```bash
python start_backend.py
```

**터미널 2 — 프론트엔드 (포트 5173)**
```bash
node frontend/node_modules/vite/bin/vite.js frontend --port 5173 --config frontend/vite.config.js
```

### 4. 접속

| 서비스 | 주소 |
|--------|------|
| 트레이딩 앱 | http://localhost:5173 |
| API 문서 (Swagger) | http://localhost:8000/docs |

---

## 프로젝트 구조

```
Trading/
├── start_backend.py        # 백엔드 실행 진입점
├── .env.example            # API 키 예시
│
├── backend/
│   ├── main.py             # FastAPI 앱
│   ├── core/
│   │   ├── upbit_client.py # Upbit REST + WebSocket
│   │   ├── strategies.py   # 매매 전략
│   │   ├── bot.py          # 자동매매 봇 엔진
│   │   └── backtest.py     # 백테스팅 엔진
│   ├── api/
│   │   ├── routes.py       # REST 엔드포인트
│   │   └── ws_handler.py   # WebSocket 핸들러
│   └── db/
│       └── database.py     # SQLite 초기화
│
└── frontend/
    └── src/
        ├── App.jsx
        └── components/
            ├── Chart.jsx       # 실시간 캔들 차트
            ├── Ticker.jsx      # 현재가
            ├── BotControl.jsx  # 봇 제어 UI
            ├── Portfolio.jsx   # 포트폴리오
            └── Backtest.jsx    # 백테스팅 UI
```

---

## API 엔드포인트

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/candles/{market}` | 캔들 데이터 |
| GET | `/api/indicators/{market}` | 기술적 지표 |
| GET | `/api/ticker/{market}` | 현재가 |
| POST | `/api/bot/start` | 봇 시작 |
| POST | `/api/bot/stop` | 봇 중지 |
| GET | `/api/bot/status` | 봇 상태 |
| POST | `/api/backtest` | 백테스트 실행 |
| GET | `/api/portfolio` | 포트폴리오 조회 |
| WS | `/ws/ticker` | 실시간 현재가 |

---

## 주의사항

> ⚠️ **실거래 모드**는 실제 자산이 사용됩니다. 반드시 **모의투자 모드**로 충분히 테스트한 후 사용하세요.
> ⚠️ 자동매매로 인한 투자 손실에 대한 책임은 사용자 본인에게 있습니다.
