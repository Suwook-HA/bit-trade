import { useState, useEffect, useRef } from 'react'
import { startBot, stopBot, getBotStatus } from '../services/api'

const STRATEGIES = [
  { value: 'rsi', label: 'RSI 과매수/과매도' },
  { value: 'macd', label: 'MACD 크로스' },
  { value: 'bollinger', label: '볼린저 밴드' },
  { value: 'ma_cross', label: 'MA 골든/데드 크로스' },
]
const DEFAULT_PARAMS = {
  rsi: { period: 14, oversold: 30, overbought: 70 },
  macd: { fast: 12, slow: 26, signal: 9 },
  bollinger: { period: 20, std_dev: 2.0 },
  ma_cross: { short_period: 5, long_period: 20 },
}

const label = { fontSize: '11px', color: '#71717a', marginBottom: '4px', display: 'block', fontWeight: 500 }
const row2 = { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }
const divider = { borderTop: '1px solid #27272a', margin: '12px 0' }

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
        ].map(({ lbl, val, col }) => (
          <div key={lbl} className="stat-card">
            <div style={{ fontSize: '10px', color: '#52525b', marginBottom: '3px' }}>{lbl}</div>
            <div style={{ fontSize: '12px', fontWeight: 700, color: col || '#fafafa' }}>{val}</div>
          </div>
        ))}
      </div>

      <div style={{ background: '#09090b', borderRadius: '6px', padding: '8px 10px', fontSize: '11px', color: '#71717a' }}>
        <span style={{ marginRight: '6px' }}>🔍</span>
        {status.last_signal_reason || '시그널 대기 중...'}
        {status.last_check && <span style={{ float: 'right', color: '#52525b' }}>{status.last_check}</span>}
      </div>
    </div>
  )
}

export default function BotControl() {
  const [strategy, setStrategy] = useState('rsi')
  const [params, setParams] = useState(DEFAULT_PARAMS.rsi)
  const [botInterval, setBotInterval] = useState('1m')
  const [mode, setMode] = useState('paper')
  const [orderRatio, setOrderRatio] = useState(0.5)
  const [stopLoss, setStopLoss] = useState(3)
  const [takeProfit, setTakeProfit] = useState(5)
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(false)
  const pollRef = useRef(null)

  useEffect(() => { setParams(DEFAULT_PARAMS[strategy]) }, [strategy])

  useEffect(() => {
    const load = async () => { try { setStatus(await getBotStatus()) } catch {} }
    load()
    pollRef.current = setInterval(load, 2000)
    return () => clearInterval(pollRef.current)
  }, [])

  const handleStart = async () => {
    setLoading(true)
    try {
      await startBot({
        market: 'KRW-BTC', interval: botInterval, strategy, params, mode,
        budget: 10000000, order_ratio: orderRatio,
        stop_loss: stopLoss / 100, take_profit: takeProfit / 100,
      })
    } catch (e) { alert('봇 시작 실패: ' + e.message) }
    setLoading(false)
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

      <div style={{ padding: '14px', flex: 1 }}>
        {status?.running ? (
          <RunningStatus status={status} />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div>
              <label style={label}>전략</label>
              <select className="select-field" value={strategy} onChange={e => setStrategy(e.target.value)}>
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

            <div style={divider} />

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
                  {['1m','3m','5m','15m','1h'].map(iv => <option key={iv} value={iv}>{iv}</option>)}
                </select>
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
              <input type="range" min={0.1} max={1} step={0.1} value={orderRatio}
                onChange={e => setOrderRatio(Number(e.target.value))}
                style={{ width: '100%', accentColor: '#3b82f6' }} />
            </div>
          </div>
        )}
      </div>

      <div style={{ padding: '0 14px 14px' }}>
        {status?.running ? (
          <button className="btn-danger" onClick={async () => { setLoading(true); await stopBot(); setLoading(false) }} disabled={loading}>
            ■ 봇 중지
          </button>
        ) : (
          <button className="btn-primary" onClick={handleStart} disabled={loading}>
            {mode === 'paper' ? '▶ 모의투자 시작' : '⚡ 실거래 시작'}
          </button>
        )}
      </div>
    </div>
  )
}
