export function createTickerWS(onMessage) {
  const ws = new WebSocket(`ws://${location.host}/ws/ticker`)

  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data)
      onMessage(data)
    } catch {}
  }

  ws.onerror = () => {}
  ws.onclose = () => {
    setTimeout(() => createTickerWS(onMessage), 3000)
  }

  return ws
}
