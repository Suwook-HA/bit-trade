import { useState, useEffect, useRef } from 'react'
import { startBot, stopBot, getBotStatus, getRecommendation } from '../services/api'

const MARKETS = [
  { value: 'KRW-BTC', label: '비트코인 (BTC)' },
  { value: 'KRW-ETH', label: '이더리움 (ETH)' },
  { value: 'KRW-SOL', label: '솔라나 (SOL)' },
  { value: 'KRW-XRP', label: '리플 (XRP)' },
]

const STRATEGIES = [
  { value: 'rsi', label: 'RSI 과매수/과매도' },
  { value: 'macd', label: 'MACD 크로스' },
  { value: 'bollinger', label: '볼린저 밴드' },
  { value: 'ma_cross', label: 'MA 골든/데드 크로스' },
  { value: 'vwap', label: 'VWAP 이탈 (스캘핑)' },
]
const DEFAULT_PARAMS = {
  rsi: { period: 14, oversold: 30, overbought: 70 },
  macd: { fast: 12, slow: 26, signal: 9 },
  bollinger: { period: 20, std_dev: 2.0 },
  ma_cross: { short_period: 5, long_period: 20 },
  vwap: { deviation: 0.003, period: 20 },
}
const SCALPING_PARAMS = {
  rsi: { period: 7, oversold: 25, overbought: 65 },
  macd: { fast: 5, slow: 13, signal: 5 },
  bollinger: { period: 10, std_dev: 1.5 },
  ma_cross: { short_period: 3, long_period: 10 },
}
const STRATEGY_LABELS = { rsi: 'RSI', macd: 'MACD', bollinger: '볼린저 밴드', ma_cross: 'MA 크로스', vwap: 'VWAP' }
const SCALPING_INTERVALS = ['5s', '10s', '15s', '30s']
const CONDITION_META = {
  trending_up:   { label: '상승 추세', color: '#34d399' },
  trending_down: { label: '하락 추세', color: '#f87171' },
  ranging:       { label: '횡보 구간', color: '#60a5fa' },
  volatile:      { label: '고변동성', color: '#f59e0b' },
  unknown:       { label: '분석 중',  color: '#71717a' },
}

const label = { fontSize: '11px', color: '#71717a', marginBottom: '4px', display: 'block', fontWeight: 500 }
const MAX_ORDER_RATIO = 0.4
const RECOMMENDATION_LOOKBACK_DAYS = 3
const SCALPING_PRESET = {
  market: 'KRW-BTC',
  strategy: 'rsi',
  params: SCALPING_PARAMS.rsi,
  botInterval: '1m',
  mode: 'paper',
  orderRatio: 0.3,
  stopLoss: 1.2,
  takeProfit: 2.0,
  autoRebalance: true,
  autoStrategy: true,
  execInterval: 10,
  budget: 1000000,
  trailingStop: true,
  trailingStopPct: 0.8,
}
const row2 = { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }
const divider = { borderTop: '1px solid #27272a', margin: '12px 0' }

// ── 추천 패널 ─────────────────────────────────────────────────
function RecommendationPanel({ data, onApply }) {
  const cond = CONDITION_META[data.market_condition?.condition] || CONDITION_META.unknown

  return (
    <div>
      {/* 시장 상태 배지 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '10px', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '11px', color: '#71717a' }}>시장 상태:</span>
        <span style={{
          padding: '2px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 700,
          background: `${cond.color}22`, color: cond.color,
        }}>{cond.label}</span>
        <span style={{ fontSize: '10px', color: '#52525b', flex: 1 }}>
          {data.market_condition?.reason}
        </span>
      </div>

      {/* 추천 카드 */}
      {data.recommendations.map((rec, i) => {
        const m = rec.metrics?.oos || {}
        return (
          <div key={i} style={{
            background: '#09090b', border: '1px solid #27272a',
            borderRadius: '8px', padding: '10px 12px', marginBottom: '8px',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
              <span style={{ fontWeight: 700, fontSize: '13px', color: '#fafafa' }}>
                {i + 1}. {STRATEGY_LABELS[rec.strategy] || rec.strategy}
              </span>
              <span style={{ fontSize: '12px', color: '#f59e0b', fontWeight: 700 }}>
                점수 {rec.score.toFixed(2)}
              </span>
            </div>
            <div style={{ fontSize: '10px', color: '#52525b', marginBottom: '6px' }}>
              {Object.entries(rec.params).map(([k, v]) => `${k}=${v}`).join(' / ')}
            </div>
            <div style={{ display: 'flex', gap: '5px', marginBottom: '8px' }}>
              {[
                { lbl: '수익률', val: `${(m.total_return_pct ?? 0) >= 0 ? '+' : ''}${m.total_return_pct ?? 0}%`, col: (m.total_return_pct ?? 0) >= 0 ? '#34d399' : '#f87171' },
                { lbl: '샤프',   val: (m.sharpe_ratio ?? 0).toFixed(2), col: '#60a5fa' },
                { lbl: '승률',   val: `${m.win_rate_pct ?? 0}%`,      col: '#a78bfa' },
              ].map(({ lbl: l, val, col }) => (
                <div key={l} style={{ flex: 1, background: '#18181b', borderRadius: '4px', padding: '4px 6px', textAlign: 'center' }}>
                  <div style={{ fontSize: '9px', color: '#52525b' }}>{l}</div>
                  <div style={{ fontSize: '11px', fontWeight: 700, color: col }}>{val}</div>
                </div>
              ))}
            </div>
            <div style={{ fontSize: '10px', color: '#71717a', marginBottom: '8px' }}>{rec.reason}</div>
            <button
              onClick={() => onApply(rec.strategy, rec.params)}
              style={{
                width: '100%', padding: '5px 0', borderRadius: '4px',
                border: '1px solid #3b82f6', background: 'rgba(59,130,246,0.1)',
                color: '#60a5fa', fontSize: '11px', fontWeight: 600, cursor: 'pointer',
              }}>
              이 전략 적용
            </button>
          </div>
        )
      })}
      <div style={{ fontSize: '10px', color: '#3f3f46', textAlign: 'right' }}>
        {data.total_combinations_tested}개 조합 분석 · {data.cached ? '캐시됨' : '실시간'}
      </div>
    </div>
  )
}

// ── 실행 중 상태 ──────────────────────────────────────────────
function RunningStatus({ status }) {
  const fmt = n => n?.toLocaleString('ko-KR')
  const pnl = status.current_pnl_pct
  const totalPnl = Math.round(status.total_pnl)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      <div style={{
        background: '#09090b', borderRadius: '8px', padding: '12px',
        border: `1px solid ${status.position === 'long' ? 'rgba(52,211,153,0.3)' : '#27272a'}`,
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
          <span style={{ fontSize: '11px', color: '#71717a', fontWeight: 600 }}>포지션</span>
          <span style={{
            padding: '2px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 700,
            background: status.position === 'long' ? 'rgba(52,211,153,0.15)' : '#27272a',
            color: status.position === 'long' ? '#34d399' : '#71717a',
          }}>
            {status.position === 'long' ? '● 롱' : '○ 없음'}
          </span>
        </div>
        {status.position === 'long' && (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
              <span style={{ fontSize: '11px', color: '#71717a' }}>진입가</span>
              <span style={{ fontSize: '11px', color: '#fafafa', fontWeight: 600 }}>₩{fmt(status.entry_price)}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '11px', color: '#71717a' }}>현재 손익</span>
              <span style={{ fontSize: '13px', fontWeight: 700, color: pnl >= 0 ? '#34d399' : '#f87171' }}>
                {pnl >= 0 ? '+' : ''}{pnl}%
              </span>
            </div>
          </>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '6px' }}>
        {[
          { lbl: '총 거래', val: `${status.total_trades}회` },
          { lbl: '누적 손익', val: `${totalPnl >= 0 ? '+' : ''}₩${fmt(Math.abs(totalPnl))}`, col: totalPnl >= 0 ? '#34d399' : '#f87171' },
          { lbl: '모의 잔고', val: `₩${fmt(Math.round(status.paper_krw / 10000))}만` },
        ].map(({ lbl: l, val, col }) => (
          <div key={l} className="stat-card">
            <div style={{ fontSize: '10px', color: '#52525b', marginBottom: '3px' }}>{l}</div>
            <div style={{ fontSize: '12px', fontWeight: 700, color: col || '#fafafa' }}>{val}</div>
          </div>
        ))}
      </div>

      {/* 자동 재조정 배지 */}
      {status.rebalancing_enabled && (
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '4px 10px', background: 'rgba(167,139,250,0.1)',
          border: '1px solid rgba(167,139,250,0.3)', borderRadius: '6px',
        }}>
          <span style={{ fontSize: '10px', color: '#a78bfa', fontWeight: 700 }}>
            ♻ 자동 재조정 ON
            {status.rebalance_count > 0 && ` (${status.rebalance_count}회)`}
          </span>
          <span style={{ fontSize: '10px', color: '#52525b' }}>
            {status.last_rebalanced ? `마지막: ${status.last_rebalanced}` : '대기 중'}
          </span>
        </div>
      )}

      <div style={{ background: '#09090b', borderRadius: '6px', padding: '8px 10px', fontSize: '11px', color: '#71717a' }}>
        <span style={{ marginRight: '6px' }}>🔍</span>
        {status.last_signal_reason || '시그널 대기 중...'}
        {status.last_check && <span style={{ float: 'right', color: '#52525b' }}>{status.last_check}</span>}
      </div>
    </div>
  )
}

// ── 메인 컴포넌트 ─────────────────────────────────────────────
export default function BotControl() {
  const [market, setMarket] = useState(SCALPING_PRESET.market)
  const [strategy, setStrategy] = useState(SCALPING_PRESET.strategy)
  const [params, setParams] = useState(SCALPING_PRESET.params)
  const [botInterval, setBotInterval] = useState(SCALPING_PRESET.botInterval)
  const [mode, setMode] = useState(SCALPING_PRESET.mode)
  const [orderRatio, setOrderRatio] = useState(SCALPING_PRESET.orderRatio)
  const [stopLoss, setStopLoss] = useState(SCALPING_PRESET.stopLoss)
  const [takeProfit, setTakeProfit] = useState(SCALPING_PRESET.takeProfit)
  const [autoRebalance, setAutoRebalance] = useState(SCALPING_PRESET.autoRebalance)
  const [autoStrategy, setAutoStrategy] = useState(SCALPING_PRESET.autoStrategy)
  const [execInterval, setExecInterval] = useState(SCALPING_PRESET.execInterval)
  const [budget, setBudget] = useState(SCALPING_PRESET.budget)
  const [trailingStop, setTrailingStop] = useState(SCALPING_PRESET.trailingStop)
  const [trailingStopPct, setTrailingStopPct] = useState(SCALPING_PRESET.trailingStopPct)
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(false)
  const [startError, setStartError] = useState(null)
  const [recommendations, setRecommendations] = useState(null)
  const [recLoading, setRecLoading] = useState(false)
  const [recError, setRecError] = useState(null)
  const pollRef = useRef(null)

  const isScalping = SCALPING_INTERVALS.includes(botInterval)
  const recommendationRequestRef = useRef(0)

  useEffect(() => { setParams(DEFAULT_PARAMS[strategy]) }, [strategy])

  useEffect(() => {
    if (SCALPING_INTERVALS.includes(botInterval)) {
      setStopLoss(0.3)
      setTakeProfit(0.5)
      setExecInterval(0)
    } else {
      setStopLoss(3)
      setTakeProfit(5)
    }
  }, [botInterval])

  useEffect(() => {
    const load = async () => { try { setStatus(await getBotStatus()) } catch {} }
    load()
    pollRef.current = setInterval(load, 2000)
    return () => clearInterval(pollRef.current)
  }, [])

  const applyRecommendation = (recStrategy, recParams) => {
    setStrategy(recStrategy)
    setParams(recParams)
  }

  const selectStrategy = nextStrategy => {
    setStrategy(nextStrategy)
    setParams(SCALPING_PARAMS[nextStrategy])
  }

  const loadRecommendation = async ({ autoApply = true } = {}) => {
    const requestId = recommendationRequestRef.current + 1
    recommendationRequestRef.current = requestId
    setRecLoading(true)
    setRecError(null)

    try {
      const data = await getRecommendation({
        market,
        interval: botInterval,
        days: RECOMMENDATION_LOOKBACK_DAYS,
      })

      if (recommendationRequestRef.current !== requestId) return null
      if (data.error) throw new Error(data.error)

      setRecommendations(data)
      if (autoApply && data.recommendations?.length) {
        const best = data.recommendations[0]
        applyRecommendation(best.strategy, best.params)
      }
      return data
    } catch (e) {
      if (recommendationRequestRef.current === requestId) {
        setRecError('추천 실패: ' + (e.response?.data?.detail || e.message))
      }
      return null
    } finally {
      if (recommendationRequestRef.current === requestId) {
        setRecLoading(false)
      }
    }
  }

  useEffect(() => {
    if (!autoStrategy) return
    loadRecommendation()
  }, [market, botInterval, autoStrategy])

  const handleStart = async () => {
    setLoading(true)
    setStartError(null)
    try {
      const result = await startBot({
        market, interval: botInterval, strategy, params, mode,
        budget, order_ratio: orderRatio,
        stop_loss: stopLoss / 100, take_profit: takeProfit / 100,
        auto_rebalance: autoRebalance,
        rebalance_interval_candles: 30,
        execution_interval_seconds: execInterval,
        trailing_stop: trailingStop,
        trailing_stop_pct: trailingStopPct / 100,
        auto_strategy: autoStrategy,
      })
      if (result?.error) throw new Error(result.error)
      setStatus(await getBotStatus())
    } catch (e) {
      setStartError('봇 시작 실패: ' + (e.response?.data?.detail || e.message))
    }
    setLoading(false)
  }

  const handleRecommend = async () => {
    await loadRecommendation()
  }

  const updateParam = (key, val) => setParams(p => ({ ...p, [key]: isNaN(Number(val)) ? val : Number(val) }))

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '12px 14px', borderBottom: '1px solid #27272a', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: '12px', fontWeight: 700, color: '#a1a1aa', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          🤖 자동매매 봇
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{
            width: '6px', height: '6px', borderRadius: '50%', display: 'inline-block',
            background: status?.running ? '#34d399' : '#3f3f46',
            boxShadow: status?.running ? '0 0 6px #34d399' : 'none',
          }} />
          <span style={{ fontSize: '11px', color: status?.running ? '#34d399' : '#71717a', fontWeight: 600 }}>
            {status?.running ? '실행 중' : '대기'}
          </span>
        </div>
      </div>

      <div style={{ padding: '14px', flex: 1, overflowY: 'auto' }}>
        {status?.running ? (
          <RunningStatus status={status} />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {/* 자동 전략 선택 */}
            <div style={{
              display: 'flex', alignItems: 'flex-start', gap: '8px',
              padding: '10px 12px', borderRadius: '8px',
              background: autoStrategy ? 'rgba(167,139,250,0.08)' : '#18181b',
              border: `1px solid ${autoStrategy ? 'rgba(167,139,250,0.4)' : '#27272a'}`,
            }}>
              <input type="checkbox" id="autoStrategy" checked={autoStrategy}
                onChange={e => setAutoStrategy(e.target.checked)}
                style={{ accentColor: '#a78bfa', width: '14px', height: '14px', marginTop: '2px', flexShrink: 0 }} />
              <div>
                <label htmlFor="autoStrategy" style={{ ...label, marginBottom: '2px', color: '#a78bfa', cursor: 'pointer', fontWeight: 700 }}>
                  자동 전략 선택
                </label>
                <div style={{ fontSize: '10px', color: '#52525b', lineHeight: 1.5 }}>
                  기본값은 스캘핑 기준(1분봉 / 10초 실행 / 짧은 손절·익절)으로 맞춰집니다.<br />
                  봇 시작 전 최근 {RECOMMENDATION_LOOKBACK_DAYS}일 기준 추천 전략을 자동 반영합니다.<br />
                  OFF이면 아래에서 직접 선택하세요.
                </div>
              </div>
            </div>

            {!autoStrategy && (<>
              <div>
                <label style={label}>전략</label>
                <select className="select-field" value={strategy} onChange={e => selectStrategy(e.target.value)}>
                  {STRATEGIES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                </select>
              </div>

              <div>
                <label style={label}>전략 파라미터</label>
                <div style={row2}>
                  {Object.entries(params).map(([key, val]) => (
                    <div key={key}>
                      <label style={{ ...label, color: '#52525b' }}>{key}</label>
                      <input type="number" value={val} onChange={e => updateParam(key, e.target.value)}
                        className="input-field" step={key.includes('std') ? 0.1 : 1} />
                    </div>
                  ))}
                </div>
              </div>
            </>)}

            <div style={divider} />

            <div>
              <label style={label}>종목</label>
              <select className="select-field" value={market} onChange={e => setMarket(e.target.value)}>
                {MARKETS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
              </select>
            </div>

            <div style={row2}>
              <div>
                <label style={label}>모드</label>
                <select className="select-field" value={mode} onChange={e => setMode(e.target.value)}>
                  <option value="paper">🎭 모의투자</option>
                  <option value="live">⚡ 실거래</option>
                </select>
              </div>
              <div>
                <label style={label}>타임프레임</label>
                <select className="select-field" value={botInterval} onChange={e => setBotInterval(e.target.value)}>
                  {['5s','10s','15s','30s','1m','3m','5m','15m','1h'].map(iv => <option key={iv} value={iv}>{iv}</option>)}
                </select>
              </div>
            </div>

            {isScalping && (
              <div style={{
                padding: '8px 12px', borderRadius: '6px', fontSize: '11px',
                background: 'rgba(251,191,36,0.08)', border: '1px solid rgba(251,191,36,0.3)',
                color: '#fbbf24', lineHeight: 1.5,
              }}>
                ⚡ 스캘핑 모드: 이벤트 주도(WebSocket tick) 루프 자동 적용<br />
                수수료+슬리피지 0.14% 기준, 익절 ≥ 0.21% 권장 (현재 {takeProfit}%)
              </div>
            )}

            {!isScalping && (
              <div>
                <label style={label}>
                  실행 주기&nbsp;
                  <span style={{ color: '#60a5fa', fontWeight: 700 }}>
                    {execInterval === 0 ? '캔들 타임프레임 동일' : `${execInterval}초`}
                  </span>
                </label>
                <select className="select-field" value={execInterval} onChange={e => setExecInterval(Number(e.target.value))}>
                  <option value={0}>타임프레임 동일 (기본)</option>
                  <option value={10}>10초</option>
                  <option value={30}>30초</option>
                  <option value={60}>1분</option>
                  <option value={120}>2분</option>
                  <option value={300}>5분</option>
                  <option value={600}>10분</option>
                  <option value={900}>15분</option>
                  <option value={1800}>30분</option>
                  <option value={3600}>1시간</option>
                </select>
              </div>
            )}

            <div>
              <label style={label}>
                투자 한도&nbsp;
                <span style={{ color: '#fbbf24', fontWeight: 700 }}>
                  {budget >= 1000000
                    ? `₩${(budget / 10000).toLocaleString()}만`
                    : `₩${budget.toLocaleString()}`}
                </span>
              </label>
              <div style={{ display: 'flex', gap: '6px' }}>
                <input
                  type="number"
                  value={budget}
                  onChange={e => setBudget(Math.max(10000, Number(e.target.value)))}
                  className="input-field"
                  min={10000}
                  step={100000}
                  style={{ flex: 1 }}
                />
                <div style={{ display: 'flex', gap: '4px' }}>
                  {[500000, 1000000, 5000000, 10000000].map(v => (
                    <button
                      key={v}
                      onClick={() => setBudget(v)}
                      style={{
                        padding: '0 8px', borderRadius: '4px', fontSize: '10px',
                        border: `1px solid ${budget === v ? '#fbbf24' : '#3f3f46'}`,
                        background: budget === v ? 'rgba(251,191,36,0.15)' : '#18181b',
                        color: budget === v ? '#fbbf24' : '#71717a',
                        cursor: 'pointer', whiteSpace: 'nowrap',
                      }}>
                      {v / 10000}만
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div style={row2}>
              <div>
                <label style={label}>손절 <span style={{ color: '#f87171' }}>{stopLoss}%</span></label>
                <input type="number" value={stopLoss} onChange={e => setStopLoss(Number(e.target.value))}
                  className="input-field" min={0.1} max={20} step={0.1} />
              </div>
              <div>
                <label style={label}>익절 <span style={{ color: '#34d399' }}>{takeProfit}%</span></label>
                <input type="number" value={takeProfit} onChange={e => setTakeProfit(Number(e.target.value))}
                  className="input-field" min={0.1} max={50} step={0.1} />
              </div>
            </div>

            <div>
              <label style={label}>
                투자 비율 &nbsp;
                <span style={{ color: '#60a5fa', fontWeight: 700 }}>{Math.round(orderRatio * 100)}%</span>
              </label>
              <input type="range" min={0.1} max={MAX_ORDER_RATIO} step={0.1} value={orderRatio}
                onChange={e => setOrderRatio(Number(e.target.value))}
                style={{ width: '100%', accentColor: '#3b82f6' }} />
              <div style={{ fontSize: '10px', color: '#52525b', marginTop: '4px' }}>
                스캘핑 기본값은 리스크 제한에 맞춰 최대 40%까지만 사용합니다.
              </div>
            </div>

            {/* 자동 재조정 체크박스 */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <input type="checkbox" id="autoRebalance" checked={autoRebalance}
                onChange={e => setAutoRebalance(e.target.checked)}
                style={{ accentColor: '#a78bfa', width: '14px', height: '14px' }} />
              <label htmlFor="autoRebalance" style={{ ...label, marginBottom: 0, color: '#a78bfa', cursor: 'pointer' }}>
                자동 재조정 (30캔들마다 전략 재평가)
              </label>
            </div>

            {/* 추적손절 */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <input type="checkbox" id="trailingStop" checked={trailingStop}
                onChange={e => setTrailingStop(e.target.checked)}
                style={{ accentColor: '#fb923c', width: '14px', height: '14px' }} />
              <label htmlFor="trailingStop" style={{ ...label, marginBottom: 0, color: '#fb923c', cursor: 'pointer' }}>
                추적손절 (고점 대비
              </label>
              <input
                type="number"
                value={trailingStopPct}
                onChange={e => setTrailingStopPct(Math.max(0.1, Number(e.target.value)))}
                disabled={!trailingStop}
                min={0.1} max={10} step={0.1}
                style={{
                  width: '52px', padding: '2px 6px', borderRadius: '4px',
                  border: `1px solid ${trailingStop ? '#fb923c' : '#3f3f46'}`,
                  background: '#18181b', color: trailingStop ? '#fb923c' : '#52525b',
                  fontSize: '12px', textAlign: 'center',
                }}
              />
              <span style={{ ...label, marginBottom: 0, color: trailingStop ? '#fb923c' : '#52525b' }}>% 하락 시 청산)</span>
            </div>

            <div style={divider} />

            {/* 전략 추천 버튼 */}
            <button
              onClick={handleRecommend}
              disabled={recLoading}
              style={{
                width: '100%', padding: '8px 0', borderRadius: '6px',
                border: '1px solid #3f3f46', background: recLoading ? '#18181b' : '#1c1c1e',
                color: recLoading ? '#52525b' : '#a1a1aa', fontSize: '12px',
                fontWeight: 600, cursor: recLoading ? 'not-allowed' : 'pointer',
              }}>
              {recLoading ? '⏳ 스캘핑 전략 분석 중...' : '🔍 스캘핑 추천 전략 새로 받기'}
            </button>

            {recError && (
              <div style={{ fontSize: '11px', color: '#f87171' }}>{recError}</div>
            )}

            {recommendations && !recLoading && (
              <RecommendationPanel
                data={recommendations}
                onApply={applyRecommendation}
              />
            )}
          </div>
        )}
      </div>

      <div style={{ padding: '0 14px 14px' }}>
        {startError && (
          <div style={{ fontSize: '11px', color: '#f87171', marginBottom: '8px', padding: '6px 10px', background: 'rgba(248,113,113,0.1)', borderRadius: '6px', border: '1px solid rgba(248,113,113,0.3)' }}>
            {startError}
          </div>
        )}
        {status?.running ? (
          <button className="btn-danger" onClick={async () => { setLoading(true); await stopBot(); setLoading(false) }} disabled={loading}>
            ■ 봇 중지
          </button>
        ) : (
          <button className="btn-primary" onClick={handleStart} disabled={loading}>
            {loading
        ? (autoStrategy ? '⏳ 전략 분석 중...' : '시작 중...')
        : mode === 'paper' ? '▶ 모의투자 시작' : '⚡ 실거래 시작'}
          </button>
        )}
      </div>
    </div>
  )
}
