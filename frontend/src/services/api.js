import axios from 'axios'

const API_KEY = import.meta.env.VITE_API_KEY || ''

const api = axios.create({
  baseURL: '/api',
  headers: API_KEY ? { 'X-API-Key': API_KEY } : {},
})

export const getCandles = (market, interval = '1m', count = 200) =>
  api.get(`/candles/${market}`, { params: { interval, count } }).then(r => r.data)

export const getIndicators = (market, interval = '1m', count = 200) =>
  api.get(`/indicators/${market}`, { params: { interval, count } }).then(r => r.data)

export const getTicker = (market) =>
  api.get(`/ticker/${market}`).then(r => r.data)

export const startBot = (config) =>
  api.post('/bot/start', config).then(r => r.data)

export const stopBot = () =>
  api.post('/bot/stop').then(r => r.data)

export const getBotStatus = () =>
  api.get('/bot/status').then(r => r.data)

export const runBacktest = (params) =>
  api.post('/backtest', params).then(r => r.data)

export const getPortfolio = () =>
  api.get('/portfolio').then(r => r.data)

export const getRecommendation = (params) =>
  api.post('/strategy/recommend', params).then(r => r.data)
