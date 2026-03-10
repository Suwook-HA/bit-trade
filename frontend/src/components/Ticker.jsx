import { useEffect, useState } from 'react'
import { createTickerWS } from '../services/websocket'

export default function Ticker({ market = 'KRW-BTC' }) {
  const [ticker, setTicker] = useState(null)
  const [prevPrice, setPrevPrice] = useState(null)
  const [flashDir, setFlashDir] = useState(null)

  useEffect(() => {
    const ws = createTickerWS((data) => {
      if (data.market === market) {
        setTicker(prev => {
          if (prev) setPrevPrice(prev.price)
          return data
        })
      }
    })
    return () => ws.close()
  }, [market])

  useEffect(() => {
    if (!ticker || !prevPrice) return
    setFlashDir(ticker.price >= prevPrice ? 'up' : 'down')
    const t = setTimeout(() => setFlashDir(null), 400)
    return () => clearTimeout(t)
  }, [ticker?.price])

  const fmt = (n) => n?.toLocaleString('ko-KR')
  const changePct = ticker?.change ? (ticker.change * 100).toFixed(2) : '0.00'
  const isPositive = parseFloat(changePct) >= 0
  const priceColor = flashDir === 'up' ? '#34d399' : flashDir === 'down' ? '#f87171' : '#fafafa'

  return (
    <div className="card" style={{ padding: '1rem 1.25rem', display: 'flex', alignItems: 'center', gap: '2rem', flexWrap: 'wrap' }}>
      {/* Market label */}
      <div>
        <div style={{ fontSize: '0.6875rem', color: '#71717a', marginBottom: '2px', fontWeight: 600, letterSpacing: '0.05em' }}>
          {market}
        </div>
        <div style={{
          fontSize: '1.875rem',
          fontWeight: 700,
          color: priceColor,
          transition: 'color 0.4s ease',
          fontVariantNumeric: 'tabular-nums',
          letterSpacing: '-0.03em',
          lineHeight: 1,
        }}>
          ₩{fmt(ticker?.price)}
        </div>
      </div>

      {/* Change */}
      <div style={{
        display: 'inline-flex', alignItems: 'center', gap: '4px',
        padding: '4px 10px',
        borderRadius: '6px',
        background: isPositive ? 'rgba(16,185,129,0.12)' : 'rgba(239,68,68,0.12)',
        border: `1px solid ${isPositive ? 'rgba(16,185,129,0.25)' : 'rgba(239,68,68,0.25)'}`,
        color: isPositive ? '#34d399' : '#f87171',
        fontSize: '0.9375rem',
        fontWeight: 700,
      }}>
        {isPositive ? '▲' : '▼'} {isPositive ? '+' : ''}{changePct}%
      </div>

      {/* Orderbook */}
      <div style={{ marginLeft: 'auto', display: 'flex', gap: '1.5rem' }}>
        <div>
          <div style={{ fontSize: '0.6875rem', color: '#71717a', marginBottom: '2px' }}>매도 (ASK)</div>
          <div style={{ fontSize: '0.875rem', fontWeight: 600, color: '#f87171', fontVariantNumeric: 'tabular-nums' }}>
            ₩{fmt(ticker?.ask_price)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: '0.6875rem', color: '#71717a', marginBottom: '2px' }}>매수 (BID)</div>
          <div style={{ fontSize: '0.875rem', fontWeight: 600, color: '#34d399', fontVariantNumeric: 'tabular-nums' }}>
            ₩{fmt(ticker?.bid_price)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: '0.6875rem', color: '#71717a', marginBottom: '2px' }}>24h 거래량</div>
          <div style={{ fontSize: '0.875rem', fontWeight: 600, color: '#a1a1aa', fontVariantNumeric: 'tabular-nums' }}>
            {ticker?.volume ? ticker.volume.toFixed(2) : '—'} BTC
          </div>
        </div>
      </div>
    </div>
  )
}
