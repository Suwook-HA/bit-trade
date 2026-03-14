export function createTickerWS(onMessage, market = 'KRW-BTC') {
  let shouldReconnect = true
  const ws = new WebSocket(`ws://${location.host}/ws/ticker?market=${market}`)

  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data)
      onMessage(data)
    } catch {}
  }

  ws.onerror = () => {}
  ws.onclose = () => {
    if (shouldReconnect) {
      setTimeout(() => createTickerWS(onMessage, market), 3000)
    }
  }

  ws.close_permanent = () => { shouldReconnect = false; ws.close() }
  return ws
}

export function createCandleWS(onUpdate, market = 'KRW-BTC') {
  let shouldReconnect = true
  const ws = new WebSocket(`ws://${location.host}/ws/candle?market=${market}`)

  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data)
      if (data.type === 'candle') onUpdate(data)
    } catch {}
  }

  ws.onerror = () => {}
  ws.onclose = () => {
    if (shouldReconnect) {
      setTimeout(() => createCandleWS(onUpdate, market), 3000)
    }
  }

  ws.close_permanent = () => { shouldReconnect = false; ws.close() }
  return ws
}
