# ₿ BTC 트레이딩 앱

업비트 API 기반 암호화폐 자동매매 웹 애플리케이션입니다.
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
- **스캘핑 인터벌**: 5s / 10s / 15s / 30s (WebSocket 틱 집계 기반)
- **일반 인터벌**: 1m / 3m / 5m / 15m / 1h / 1d
- 이동평균선 (MA 5/20/60) · 볼린저밴드 오버레이
- WebSocket 실시간 현재가 · 캔들 업데이트
- 멀티마켓 지원 (KRW-BTC / KRW-ETH / KRW-SOL / KRW-XRP)

### 🤖 자동매매 봇
- **전략**: RSI · MACD · 볼린저밴드 · MA 크로스 · **VWAP 이탈 (스캘핑)**
- **모드**: 모의투자(페이퍼) / 실거래
- **스캘핑 모드**: 5s~30s 서브분봉, TickAggregator 이벤트 주도 루프, 타이트한 리스크 프리셋
- **자동 전략 선택**: 봇 시작 시 54개+ 조합 백테스트로 최적 전략 자동 세팅
- **리스크 엔진**: 일일 손실 한도 · 연속 손실 제한 · Circuit Breaker · 최대 포지션 수 · 자산 비중 제한
- 손절(Stop Loss) · 익절(Take Profit) · 추적손절(Trailing Stop) 설정
- 투자 한도 · 투자 비율 슬라이더 (10~100%)
- 실행 주기 독립 설정 (캔들 타임프레임과 분리)
- 자동 재조정: N캔들마다 전략 재평가 후 자동 전환
- 수수료(0.05%) · 슬리피지(0.02%) 자동 반영
- 거래량 확인 필터 (저거래량 허위 신호 제거)
- 멀티마켓 동시 운용 (봇별 독립 RiskEngine)
- 감사 로그 (전략 전환 · 리스크 차단 · Circuit Breaker 이벤트)
- API 키 인증 (`X-API-Key` 헤더)

### 📊 백테스팅
- 전략별 과거 데이터 시뮬레이션 (스캘핑 인터벌 포함)
- 총 수익률 · 승률 · MDD · Sharpe Ratio · Sortino Ratio · 자산 곡선
- 추적손절 포함 시뮬레이션
- 수수료 · 슬리피지 실제 반영

### 🔍 전략 추천 (그리드 서치)
- 54개+ 전략×파라미터 조합 병렬 백테스트 (VWAP 스캘핑 포함)
- **In-sample / Out-of-sample (70/30) 분리** — 과최적화 감지
- 단타 최적화 파라미터 (RSI 5/7/9, MACD 5/13/5, 볼린저 7봉, VWAP deviation 0.1~0.5%)
- 시장 상태 분석 (상승추세 / 하락추세 / 횡보 / 고변동성)
- 상위 3개 전략 추천 + 한 번에 적용
- 5분 캐시로 반복 요청 최적화

### 💼 포트폴리오
- 모의/실거래 KRW · 자산 잔고 현황
- **누적 손익 분석**: 총 손익 · 승/패 횟수 · 승률 · 최대수익 · 최대손실
- 전체 거래 내역 (전략명 · 가격 · 단건 손익 표시)

---

## 설치 및 실행

### 사전 요구사항
- Python 3.12+
- Node.js 18+

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
APP_API_KEY=임의의_강력한_키  # 봇 시작/중지 API 보호 (선택사항)
```
> 모의투자만 사용할 경우 `.env` 없이도 동작합니다.

### 3. 서버 실행

**터미널 1 — 백엔드 (포트 8000)**
```bash
python start_backend.py
```

**터미널 2 — 프론트엔드 (포트 5173)**
```bash
cd frontend
npm run dev
```

### 4. 접속

| 서비스 | 주소 |
|--------|------|
| 트레이딩 앱 | http://localhost:5173 |
| API 문서 (Swagger) | http://localhost:8000/docs |

---

## 프로젝트 구조

```
bit-trade/
├── start_backend.py        # 백엔드 실행 진입점
├── .env.example            # API 키 예시
│
├── backend/
│   ├── main.py             # FastAPI 앱
│   ├── core/
│   │   ├── upbit_client.py # Upbit REST + WebSocket + TickAggregator
│   │   ├── strategies.py   # 매매 전략 (RSI/MACD/볼린저/MA크로스/VWAP)
│   │   ├── bot.py          # 자동매매 봇 (폴링 + 이벤트 주도 스캘핑)
│   │   ├── backtest.py     # 백테스팅 엔진
│   │   ├── recommender.py  # 그리드 서치 · 전략 자동 추천 · 과최적화 감지
│   │   ├── risk_engine.py  # 리스크 관리 (손실 한도/Circuit Breaker)
│   │   └── auth.py         # API 키 인증 (X-API-Key)
│   ├── api/
│   │   ├── routes.py       # REST 엔드포인트
│   │   └── ws_handler.py   # WebSocket 핸들러 (마켓별 구독 관리)
│   ├── db/
│   │   └── database.py     # SQLite 초기화
│   └── tests/
│       └── test_risk_engine.py  # 리스크 엔진 테스트
│
└── frontend/
    └── src/
        ├── App.jsx
        ├── services/
        │   ├── api.js          # axios 인스턴스
        │   └── websocket.js    # Ticker · Candle WebSocket
        └── components/
            ├── Chart.jsx       # 실시간 캔들 차트
            ├── Ticker.jsx      # 현재가
            ├── BotControl.jsx  # 봇 제어 UI (스캘핑/추천 패널)
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
| POST | `/api/strategy/recommend` | 전략 자동 추천 (그리드 서치) |
| GET | `/api/portfolio` | 포트폴리오 · 손익 분석 조회 |
| GET | `/api/trades` | 거래 내역 조회 |
| GET | `/api/audit-log` | 감사 로그 조회 |
| WS | `/ws/ticker?market=KRW-BTC` | 실시간 현재가 |
| WS | `/ws/candle?market=KRW-BTC` | 실시간 캔들 업데이트 |

---

## 주의사항

> ⚠️ **실거래 모드**는 실제 자산이 사용됩니다. 반드시 **모의투자 모드**로 충분히 테스트한 후 사용하세요.
> ⚠️ 자동매매로 인한 투자 손실에 대한 책임은 사용자 본인에게 있습니다.
