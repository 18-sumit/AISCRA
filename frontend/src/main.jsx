import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { error: null, info: null }
  }
  componentDidCatch(error, info) {
    this.setState({ error, info })
    console.error('App crashed:', error, info)
  }
  render() {
    if (this.state.error) {
      return (
        <div style={{
          padding: '40px', fontFamily: 'monospace', background: '#0d1117',
          color: '#f87171', minHeight: '100vh', fontSize: '13px',
        }}>
          <div style={{ color: '#f59e0b', fontSize: '16px', marginBottom: '16px' }}>
            ⚠ App crashed — check browser console (F12)
          </div>
          <pre style={{ color: '#f87171', whiteSpace: 'pre-wrap', marginBottom: '16px' }}>
            {this.state.error?.toString()}
          </pre>
          <pre style={{ color: '#8b949e', whiteSpace: 'pre-wrap', fontSize: '11px' }}>
            {this.state.info?.componentStack}
          </pre>
        </div>
      )
    }
    return this.props.children
  }
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>
)
