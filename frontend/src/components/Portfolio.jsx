import { useEffect, useState } from 'react'
import { getPortfolio } from '../services/api'

export default function Portfolio() {
  const [data, setData] = useState(null)

  useEffect(() => {
    const load = async () => { try { setData(await getPortfolio()) } catch {} }
    load()
    const t = setInterval(load, 5000)
    return () => clearInterval(t)
  }, [])

  const fmt = n => n?.toLocaleString('ko-KR')
  const trades = data?.recent_trades || []
  const portfolio = data?.paper_portfolio
  const pnl = data?.pnl_summary

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ padding: '12px 14px', borderBottom: '1px solid #27272a' }}>
        <span style={{ fontSize: '12px', fontWeight: 700, color: '#a1a1aa', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          💼 포트폴리오
        </span>
      </div>

      {/* Paper balance */}
      {portfolio && (
        <div style={{ padding: '12px 14px', borderBottom: '1px solid #27272a', display: 'flex', gap: '16px' }}>
          <div className="stat-card" style={{ flex: 1 }}>
            <div style={{ fontSize: '10px', color: '#52525b', marginBottom: '4px' }}>모의 KRW 잔고</div>
            <div style={{ fontSize: '15px', fontWeight: 700, color: '#60a5fa', fontVariantNumeric: 'tabular-nums' }}>
              ₩{fmt(Math.round(portfolio.krw))}
            </div>
          </div>
          <div className="stat-card" style={{ flex: 1 }}>
            <div style={{ fontSize: '10px', color: '#52525b', marginBottom: '4px' }}>BTC 보유량</div>
            <div style={{ fontSize: '15px', fontWeight: 700, color: '#fbbf24', fontVariantNumeric: 'tabular-nums' }}>
              {portfolio.btc?.toFixed(6)} BTC
            </div>
          </div>
        </div>
      )}

      {/* P&L Summary */}
      {pnl && pnl.trade_count > 0 && (
        <div style={{ padding: '12px 14px', borderBottom: '1px solid #27272a' }}>
          <div style={{ fontSize: '10px', color: '#52525b', fontWeight: 600, marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            누적 손익 분석
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '6px', marginBottom: '8px' }}>
            {/* 총 손익 */}
            <div style={{
              background: pnl.total_pnl >= 0 ? 'rgba(52,211,153,0.08)' : 'rgba(248,113,113,0.08)',
              border: `1px solid ${pnl.total_pnl >= 0 ? 'rgba(52,211,153,0.25)' : 'rgba(248,113,113,0.25)'}`,
              borderRadius: '8px', padding: '8px', textAlign: 'center',
            }}>
              <div style={{ fontSize: '9px', color: '#52525b', marginBottom: '3px', textTransform: 'uppercase' }}>총 손익</div>
              <div style={{ fontSize: '13px', fontWeight: 800, color: pnl.total_pnl >= 0 ? '#34d399' : '#f87171', fontVariantNumeric: 'tabular-nums' }}>
                {pnl.total_pnl >= 0 ? '+' : ''}₩{fmt(Math.abs(pnl.total_pnl))}
              </div>
            </div>
            {/* 승/패 */}
            <div style={{ background: '#18181b', border: '1px solid #27272a', borderRadius: '8px', padding: '8px', textAlign: 'center' }}>
              <div style={{ fontSize: '9px', color: '#52525b', marginBottom: '3px', textTransform: 'uppercase' }}>승 / 패</div>
              <div style={{ fontSize: '13px', fontWeight: 800, fontVariantNumeric: 'tabular-nums' }}>
                <span style={{ color: '#34d399' }}>{pnl.win_count}</span>
                <span style={{ color: '#52525b', fontSize: '11px' }}> / </span>
                <span style={{ color: '#f87171' }}>{pnl.loss_count}</span>
              </div>
              <div style={{ fontSize: '9px', color: '#71717a', marginTop: '1px' }}>승률 {pnl.win_rate_pct}%</div>
            </div>
            {/* 거래 수 */}
            <div style={{ background: '#18181b', border: '1px solid #27272a', borderRadius: '8px', padding: '8px', textAlign: 'center' }}>
              <div style={{ fontSize: '9px', color: '#52525b', marginBottom: '3px', textTransform: 'uppercase' }}>총 거래</div>
              <div style={{ fontSize: '13px', fontWeight: 800, color: '#a1a1aa' }}>{pnl.trade_count}회</div>
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px' }}>
            <div style={{ background: '#18181b', border: '1px solid #27272a', borderRadius: '6px', padding: '6px 10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '10px', color: '#52525b' }}>최대 수익</span>
              <span style={{ fontSize: '11px', fontWeight: 700, color: '#34d399', fontVariantNumeric: 'tabular-nums' }}>
                +₩{fmt(pnl.best_trade)}
              </span>
            </div>
            <div style={{ background: '#18181b', border: '1px solid #27272a', borderRadius: '6px', padding: '6px 10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '10px', color: '#52525b' }}>최대 손실</span>
              <span style={{ fontSize: '11px', fontWeight: 700, color: '#f87171', fontVariantNumeric: 'tabular-nums' }}>
                ₩{fmt(pnl.worst_trade)}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Trade history */}
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '10px 14px 6px', fontSize: '11px', color: '#52525b', fontWeight: 600 }}>
          최근 거래 내역
        </div>

        {trades.length === 0 ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#3f3f46', fontSize: '13px' }}>
            거래 내역이 없습니다
          </div>
        ) : (
          <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px 8px' }}>
            {trades.map((t, i) => (
              <div key={i} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '8px 8px', borderRadius: '6px', marginBottom: '2px',
                background: i % 2 === 0 ? 'transparent' : '#1c1c1f',
                transition: 'background 0.1s',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span className={t.side === 'buy' ? 'tag-buy' : 'tag-sell'}>
                    {t.side === 'buy' ? '매수' : '매도'}
                  </span>
                  <span style={{ fontSize: '10px', color: '#3f3f46', background: '#27272a', padding: '1px 5px', borderRadius: '3px' }}>
                    {t.mode === 'paper' ? '모의' : '실거래'}
                  </span>
                  {t.synthetic && (
                    <span style={{ fontSize: '10px', color: '#60a5fa', background: 'rgba(96,165,250,0.1)', padding: '1px 5px', borderRadius: '3px' }}>
                      시작 복원
                    </span>
                  )}
                  {t.strategy && !t.synthetic && (
                    <span style={{ fontSize: '10px', color: '#52525b' }}>{t.strategy}</span>
                  )}
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: '12px', fontWeight: 600, color: '#fafafa', fontVariantNumeric: 'tabular-nums' }}>
                    ₩{fmt(Math.round(t.price))}
                  </div>
                  {t.side === 'sell' && t.pnl !== undefined && (
                    <div style={{ fontSize: '11px', fontWeight: 700, color: t.pnl >= 0 ? '#34d399' : '#f87171' }}>
                      {t.pnl >= 0 ? '+' : ''}₩{fmt(Math.round(t.pnl))}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
