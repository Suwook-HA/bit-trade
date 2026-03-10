import { useState } from 'react'
import { runBacktest } from '../services/api'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine } from 'recharts'

const STRATEGIES = [
  { value: 'rsi', label: 'RSI' },
  { value: 'macd', label: 'MACD' },
  { value: 'bollinger', label: '볼린저 밴드' },
  { value: 'ma_cross', label: 'MA 크로스' },
]
const DEFAULT_PARAMS = {
  rsi: { period: 14, oversold: 30, overbought: 70 },
  macd: { fast: 12, slow: 26, signal: 9 },
  bollinger: { period: 20, std_dev: 2.0 },
  ma_cross: { short_period: 5, long_period: 20 },
}

const fmt = n => n?.toLocaleString('ko-KR')
const fmtDate = ts => {
  const d = new Date(ts * 1000)
  return `${d.getMonth()+1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2,'0')}`
}

const label = { fontSize: '11px', color: '#71717a', marginBottom: '4px', display: 'block', fontWeight: 500 }
const row2 = { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }

function MetricCard({ label: lbl, value, sub, color = '#fafafa', accent }) {
  return (
    <div style={{
      background: accent ? `linear-gradient(135deg, ${accent}18, ${accent}08)` : '#27272a',
      border: `1px solid ${accent ? `${accent}30` : '#3f3f46'}`,
      borderRadius: '8px', padding: '12px', textAlign: 'center',
    }}>
      <div style={{ fontSize: '10px', color: '#52525b', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{lbl}</div>
      <div style={{ fontSize: '18px', fontWeight: 800, color, letterSpacing: '-0.02em', fontVariantNumeric: 'tabular-nums' }}>{value}</div>
      {sub && <div style={{ fontSize: '10px', color: '#52525b', marginTop: '2px' }}>{sub}</div>}
    </div>
  )
}

export default function Backtest() {
  const [strategy, setStrategy] = useState('rsi')
  const [params, setParams] = useState(DEFAULT_PARAMS.rsi)
  const [interval, setInterval] = useState('5m')
  const [days, setDays] = useState(7)
  const [stopLoss, setStopLoss] = useState(3)
  const [takeProfit, setTakeProfit] = useState(5)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleStrategyChange = s => { setStrategy(s); setParams(DEFAULT_PARAMS[s]) }
  const updateParam = (key, val) => setParams(p => ({ ...p, [key]: isNaN(Number(val)) ? val : Number(val) }))

  const handleRun = async () => {
    setLoading(true); setError(''); setResult(null)
    try {
      const r = await runBacktest({
        market: 'KRW-BTC', interval, strategy, params, days,
        initial_budget: 10000000, stop_loss: stopLoss / 100, take_profit: takeProfit / 100,
      })
      if (r.error) setError(r.error)
      else setResult(r)
    } catch (e) { setError('백테스트 실행 실패: ' + e.message) }
    setLoading(false)
  }

  const { summary, equity_curve, trades } = result || {}
  const ret = summary?.total_return_pct || 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {/* Config Card */}
      <div className="card">
        <div style={{ padding: '12px 14px', borderBottom: '1px solid #27272a' }}>
          <span style={{ fontSize: '12px', fontWeight: 700, color: '#a1a1aa', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            📊 백테스팅 설정
          </span>
        </div>
        <div style={{ padding: '14px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '10px' }}>
            <div>
              <label style={label}>전략</label>
              <select className="select-field" value={strategy} onChange={e => handleStrategyChange(e.target.value)}>
                {STRATEGIES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
            </div>
            <div>
              <label style={label}>타임프레임</label>
              <select className="select-field" value={interval} onChange={e => setInterval(e.target.value)}>
                {['1m','5m','15m','1h'].map(iv => <option key={iv} value={iv}>{iv}</option>)}
              </select>
            </div>
            <div>
              <label style={label}>기간 (일)</label>
              <input type="number" value={days} onChange={e => setDays(Number(e.target.value))}
                min={1} max={90} className="input-field" />
            </div>
            <div style={row2}>
              <div>
                <label style={label}>손절%</label>
                <input type="number" value={stopLoss} onChange={e => setStopLoss(Number(e.target.value))}
                  min={0.1} max={20} step={0.1} className="input-field" />
              </div>
              <div>
                <label style={label}>익절%</label>
                <input type="number" value={takeProfit} onChange={e => setTakeProfit(Number(e.target.value))}
                  min={0.1} max={50} step={0.1} className="input-field" />
              </div>
            </div>
          </div>

          {/* Params */}
          <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-end' }}>
            {Object.entries(params).map(([key, val]) => (
              <div key={key} style={{ flex: 1 }}>
                <label style={{ ...label, color: '#52525b' }}>{key}</label>
                <input type="number" value={val} onChange={e => updateParam(key, e.target.value)}
                  step={key.includes('std') ? 0.1 : 1} className="input-field" />
              </div>
            ))}
            <div style={{ flex: 2 }}>
              <button className="btn-violet" onClick={handleRun} disabled={loading}
                style={{ height: '32px', fontSize: '13px' }}>
                {loading ? '분석 중...' : '▶ 백테스트 실행'}
              </button>
            </div>
          </div>

          {error && (
            <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '6px', padding: '8px 12px', fontSize: '12px', color: '#f87171' }}>
              {error}
            </div>
          )}
        </div>
      </div>

      {/* Results */}
      {summary && (
        <>
          {/* Metrics */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: '8px' }}>
            <MetricCard lbl="총 수익률" value={`${ret >= 0 ? '+' : ''}${ret}%`}
              color={ret >= 0 ? '#34d399' : '#f87171'}
              accent={ret >= 0 ? '#34d399' : '#f87171'} />
            <MetricCard lbl="최종 자산" value={`₩${fmt(summary.final_value)}`}
              sub={`초기 ₩${fmt(summary.initial_budget)}`}
              color={ret >= 0 ? '#34d399' : '#f87171'} />
            <MetricCard lbl="총 거래" value={`${summary.total_trades}회`} />
            <MetricCard lbl="승률" value={`${summary.win_rate_pct}%`}
              color={summary.win_rate_pct >= 50 ? '#34d399' : '#f87171'} />
            <MetricCard lbl="MDD" value={`${summary.mdd_pct}%`} color="#f87171" accent="#f87171" />
            <MetricCard lbl="Sharpe" value={summary.sharpe_ratio}
              color={summary.sharpe_ratio >= 1 ? '#34d399' : summary.sharpe_ratio >= 0 ? '#fbbf24' : '#f87171'} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: '12px' }}>
            {/* Equity Curve */}
            {equity_curve?.length > 0 && (
              <div className="card">
                <div className="card-header">자산 곡선 (Equity Curve)</div>
                <div style={{ padding: '12px' }}>
                  <ResponsiveContainer width="100%" height={220}>
                    <LineChart data={equity_curve} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                      <XAxis dataKey="time" tickFormatter={fmtDate}
                        tick={{ fontSize: 10, fill: '#52525b' }} interval="preserveStartEnd" />
                      <YAxis tick={{ fontSize: 10, fill: '#52525b' }}
                        tickFormatter={v => `${(v/1000000).toFixed(1)}M`} domain={['auto','auto']} />
                      <ReferenceLine y={10000000} stroke="#3f3f46" strokeDasharray="4 4" />
                      <Tooltip formatter={v => [`₩${fmt(v)}`, '자산']} labelFormatter={fmtDate}
                        contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: '6px', fontSize: 11 }} />
                      <Line type="monotone" dataKey="value" stroke="#60a5fa" dot={false} strokeWidth={2} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {/* Trade list */}
            {trades?.length > 0 && (
              <div className="card">
                <div className="card-header">매매 내역 (최근 {Math.min(trades.length, 20)}건)</div>
                <div style={{ overflowY: 'auto', maxHeight: '260px', padding: '4px 8px' }}>
                  {trades.slice(-20).reverse().map((t, i) => (
                    <div key={i} style={{
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      padding: '6px 6px', borderRadius: '4px',
                      background: i % 2 === 0 ? 'transparent' : '#1c1c1f',
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span className={t.side === 'buy' ? 'tag-buy' : 'tag-sell'}>
                          {t.side === 'buy' ? '매수' : '매도'}
                        </span>
                        <span style={{ fontSize: '10px', color: '#52525b' }}>{fmtDate(t.time)}</span>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ fontSize: '11px', color: '#fafafa', fontVariantNumeric: 'tabular-nums' }}>₩{fmt(Math.round(t.price))}</div>
                        {t.pnl !== undefined && (
                          <div style={{ fontSize: '11px', fontWeight: 700, color: t.pnl >= 0 ? '#34d399' : '#f87171' }}>
                            {t.pnl >= 0 ? '+' : ''}{t.pnl_pct}%
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
