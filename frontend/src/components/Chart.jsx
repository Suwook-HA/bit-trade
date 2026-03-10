import { useEffect, useRef, useState } from 'react'
import { createChart, CrosshairMode } from 'lightweight-charts'
import { getCandles, getIndicators } from '../services/api'
import { createTickerWS } from '../services/websocket'

const INTERVALS = ['1m', '3m', '5m', '15m', '1h', '1d']
const MARKET = 'KRW-BTC'

export default function Chart() {
  const containerRef = useRef(null)
  const chartRef = useRef(null)
  const candleSeriesRef = useRef(null)
  const indicatorSeriesRef = useRef({})
  const [interval, setIntervalState] = useState('1m')
  const [showBB, setShowBB] = useState(false)
  const [showMA, setShowMA] = useState(true)
  const wsRef = useRef(null)
  const lastCandleRef = useRef(null)

  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      layout: { background: { color: '#18181b' }, textColor: '#71717a' },
      grid: { vertLines: { color: '#27272a' }, horzLines: { color: '#27272a' } },
      crosshair: { mode: CrosshairMode.Normal, vertLine: { color: '#3f3f46' }, horzLine: { color: '#3f3f46' } },
      rightPriceScale: { borderColor: '#27272a', textColor: '#71717a' },
      timeScale: { borderColor: '#27272a', timeVisible: true, secondsVisible: false, textColor: '#71717a' },
      width: containerRef.current.clientWidth,
      height: 420,
    })
    const candleSeries = chart.addCandlestickSeries({
      upColor: '#34d399', downColor: '#f87171',
      borderUpColor: '#34d399', borderDownColor: '#f87171',
      wickUpColor: '#34d399', wickDownColor: '#f87171',
    })
    chartRef.current = chart
    candleSeriesRef.current = candleSeries
    const handleResize = () => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth })
    }
    window.addEventListener('resize', handleResize)
    return () => { window.removeEventListener('resize', handleResize); chart.remove() }
  }, [])

  useEffect(() => {
    if (!candleSeriesRef.current) return
    Object.values(indicatorSeriesRef.current).forEach(s => { try { chartRef.current?.removeSeries(s) } catch {} })
    indicatorSeriesRef.current = {}
    getCandles(MARKET, interval, 200).then(data => {
      if (!data.candles?.length) return
      candleSeriesRef.current?.setData(data.candles)
      lastCandleRef.current = data.candles[data.candles.length - 1]
      chartRef.current?.timeScale().fitContent()
    })
    getIndicators(MARKET, interval, 200).then(data => {
      if (!chartRef.current || !data) return
      if (showMA) {
        const colors = { ma5: '#fbbf24', ma20: '#60a5fa', ma60: '#a78bfa' }
        ;['ma5', 'ma20', 'ma60'].forEach(key => {
          if (data[key]?.length) {
            const s = chartRef.current.addLineSeries({ color: colors[key], lineWidth: 1, lastValueVisible: false, priceLineVisible: false })
            s.setData(data[key])
            indicatorSeriesRef.current[key] = s
          }
        })
      }
      if (showBB) {
        const bbStyles = [
          { color: '#6366f1', lineWidth: 1, lineStyle: 0 },
          { color: '#6366f1', lineWidth: 1, lineStyle: 2 },
          { color: '#6366f1', lineWidth: 1, lineStyle: 0 },
        ]
        ;['bb_upper', 'bb_mid', 'bb_lower'].forEach((key, i) => {
          if (data[key]?.length) {
            const s = chartRef.current.addLineSeries({ ...bbStyles[i], lastValueVisible: false, priceLineVisible: false })
            s.setData(data[key])
            indicatorSeriesRef.current[key] = s
          }
        })
      }
    })
  }, [interval, showMA, showBB])

  useEffect(() => {
    if (wsRef.current) wsRef.current.close()
    wsRef.current = createTickerWS((data) => {
      if (data.type !== 'ticker' || data.market !== MARKET) return
      if (!candleSeriesRef.current || !lastCandleRef.current) return
      const now = Math.floor(Date.now() / 1000)
      const secs = { '1m':60,'3m':180,'5m':300,'15m':900,'1h':3600,'1d':86400 }[interval] || 60
      const candleTime = Math.floor(now / secs) * secs
      const last = lastCandleRef.current
      if (candleTime === last.time) {
        const updated = { ...last, high: Math.max(last.high, data.price), low: Math.min(last.low, data.price), close: data.price }
        candleSeriesRef.current.update(updated)
        lastCandleRef.current = updated
      } else if (candleTime > last.time) {
        const newCandle = { time: candleTime, open: data.price, high: data.price, low: data.price, close: data.price }
        candleSeriesRef.current.update(newCandle)
        lastCandleRef.current = newCandle
      }
    })
    return () => wsRef.current?.close()
  }, [interval])

  const IndicatorBtn = ({ label, active, onClick, color }) => (
    <button onClick={onClick} style={{
      padding: '3px 10px', borderRadius: '4px', fontSize: '11px', fontWeight: 600,
      border: `1px solid ${active ? color : '#3f3f46'}`,
      background: active ? `${color}20` : 'transparent',
      color: active ? color : '#71717a',
      cursor: 'pointer', transition: 'all 0.15s',
    }}>{label}</button>
  )

  return (
    <div className="card" style={{ overflow: 'hidden' }}>
      {/* Toolbar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '8px',
        padding: '10px 12px', borderBottom: '1px solid #27272a',
      }}>
        {/* Interval pills */}
        <div style={{ display: 'flex', gap: '2px', background: '#09090b', borderRadius: '6px', padding: '2px' }}>
          {INTERVALS.map(iv => (
            <button key={iv} onClick={() => setIntervalState(iv)}
              className={interval === iv ? 'pill-active' : 'pill-inactive'}
              style={{ padding: '3px 10px', fontSize: '12px' }}
            >{iv}</button>
          ))}
        </div>
        <div style={{ width: '1px', height: '20px', background: '#27272a', margin: '0 4px' }} />
        <IndicatorBtn label="MA" active={showMA} onClick={() => setShowMA(v => !v)} color="#fbbf24" />
        <IndicatorBtn label="BB" active={showBB} onClick={() => setShowBB(v => !v)} color="#6366f1" />
        <div style={{ marginLeft: 'auto', fontSize: '11px', color: '#52525b' }}>KRW-BTC · Upbit</div>
      </div>
      <div ref={containerRef} />
    </div>
  )
}
