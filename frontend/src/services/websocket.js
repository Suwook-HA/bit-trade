export function createTickerWS(onMessage, market = 'KRW-BTC') {
  const ws = new WebSocket(`ws://${location.host}/ws/ticker?market=${market}`)

  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data)
      onMessage(data)
    } catch {}
  }

  ws.onerror = () => {}
  ws.onclose = () => {
    setTimeout(() => createTickerWS(onMessage, market), 3000)
  }

  return ws
}

export function createCandleWS(onUpdate, market = 'KRW-BTC') {
  const ws = new WebSocket(`ws://${location.host}/ws/candle?market=${market}`)

  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data)
      if (data.type === 'candle_update') onUpdate(data)
    } catch {}
  }

  ws.onerror = () => {}
  ws.onclose = () => {
    setTimeout(() => createCandleWS(onUpdate, market), 3000)
  }

  return ws
}
