import { useState } from 'react'
import Chart from './components/Chart'
import Ticker from './components/Ticker'
import BotControl from './components/BotControl'
import Portfolio from './components/Portfolio'
import Backtest from './components/Backtest'

const TABS = [
  { id: 'chart', label: '📈 차트', icon: '📈' },
  { id: 'bot', label: '🤖 자동매매', icon: '🤖' },
  { id: 'backtest', label: '📊 백테스팅', icon: '📊' },
  { id: 'portfolio', label: '💼 포트폴리오', icon: '💼' },
]

export default function App() {
  const [activeTab, setActiveTab] = useState('chart')

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#09090b', color: '#fafafa' }}>
      {/* Header */}
      <header style={{
        background: 'linear-gradient(180deg, #18181b 0%, #111113 100%)',
        borderBottom: '1px solid #27272a',
        padding: '0 1.25rem',
        height: '52px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        position: 'sticky',
        top: 0,
        zIndex: 50,
        backdropFilter: 'blur(12px)',
      }}>
        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
          <div style={{
            width: '28px', height: '28px',
            background: 'linear-gradient(135deg, #f59e0b, #d97706)',
            borderRadius: '6px',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '14px', fontWeight: 700,
          }}>₿</div>
          <span style={{ fontWeight: 700, fontSize: '0.9375rem', letterSpacing: '-0.02em' }}>
            BTC <span style={{ color: '#71717a', fontWeight: 400 }}>트레이딩</span>
          </span>
        </div>

        {/* Nav Tabs */}
        <nav style={{ display: 'flex', gap: '2px', background: '#09090b', borderRadius: '8px', padding: '3px' }}>
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={activeTab === tab.id ? 'pill-active' : 'pill-inactive'}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </header>

      {/* Main */}
      <main style={{ maxWidth: '1400px', margin: '0 auto', padding: '1rem 1.25rem', display: 'flex', flexDirection: 'column', gap: '0.875rem' }}>
        <Ticker market="KRW-BTC" />

        {activeTab === 'chart' && <Chart />}

        {activeTab === 'bot' && (
          <div style={{ display: 'grid', gridTemplateColumns: '360px 1fr', gap: '0.875rem' }}>
            <BotControl />
            <Portfolio />
          </div>
        )}

        {activeTab === 'backtest' && <Backtest />}
        {activeTab === 'portfolio' && <Portfolio />}
      </main>
    </div>
  )
}
