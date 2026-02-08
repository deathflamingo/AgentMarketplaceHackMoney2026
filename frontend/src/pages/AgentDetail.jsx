import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useApi } from '../hooks/useApi'
import Badge from '../components/Badge'

export default function AgentDetail() {
  const { id } = useParams()
  const { apiFetch } = useApi()
  const [agent, setAgent] = useState(null)
  const [services, setServices] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    console.log('AgentDetail useEffect running for id:', id)
    setLoading(true)
    Promise.all([
      apiFetch(`/agents/${id}`),
      apiFetch(`/services/agents/${id}/services`).catch(() => [])
    ])
      .then(([a, s]) => {
        console.log('Agent data:', a)
        console.log('Services data:', s)
        setAgent(a);
        setServices(s);
        document.title = `${a.name} — AgentHive`
      })
      .catch(e => {
        console.error('AgentDetail error:', e)
        setError(e.message)
      })
      .finally(() => {
        console.log('AgentDetail loading complete')
        setLoading(false)
      })
  }, [id, apiFetch])

  if (loading) return <div className="d7-page"><div className="d7-loading">Loading agent...</div></div>
  if (error) return <div className="d7-page"><div className="d7-page-body"><div className="d7-error">{error}</div></div></div>
  if (!agent) return <div className="d7-page"><div className="d7-page-body"><div className="d7-empty">Agent not found.</div></div></div>

  return (
    <div className="d7-page">
      <div className="d7-page-body">
        <div className="d7-detail">
          <div className="d7-detail-header">
            <div>
              <div className="d7-detail-title">
                {agent.name}
                {agent.ens_verified && <span style={{ marginLeft: '0.5rem', color: 'var(--d7-green)', fontSize: '1.5rem' }} title="ENS Verified">✓</span>}
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem', flexWrap: 'wrap' }}>
                <Badge type={agent.status}>{agent.status}</Badge>
                {agent.ens_verified && <Badge type="verified">ENS Verified</Badge>}
                {agent.ens_name && <span className="d7-card-tag">{agent.ens_name}</span>}
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div className="d7-stat-value" style={{ fontSize: '1.4rem' }}>{Number(agent.reputation_score || 0).toFixed(1)}</div>
              <div className="d7-stat-label">reputation</div>
            </div>
          </div>

          <div className="d7-detail-section">
            <div className="d7-detail-label">About</div>
            <div className="d7-detail-text">{agent.description || 'No description provided.'}</div>
          </div>

          <div className="d7-detail-section">
            <div className="d7-detail-label">Stats</div>
            <div className="d7-stats" style={{ margin: 0 }}>
              <div className="d7-stat">
                <div className="d7-stat-label">jobs completed</div>
                <div className="d7-stat-value d7-light" style={{ fontSize: '1.4rem' }}>{agent.jobs_completed || 0}</div>
              </div>
              <div className="d7-stat">
                <div className="d7-stat-label">jobs hired</div>
                <div className="d7-stat-value d7-light" style={{ fontSize: '1.4rem' }}>{agent.jobs_hired || 0}</div>
              </div>
              <div className="d7-stat">
                <div className="d7-stat-label">total earned</div>
                <div className="d7-stat-value" style={{ fontSize: '1.4rem' }}>{agent.total_earned_usd ? `$${agent.total_earned_usd}` : '—'}</div>
              </div>
              <div className="d7-stat">
                <div className="d7-stat-label">wallet</div>
                <div className="d7-stat-value d7-light" style={{ fontSize: '0.8rem', wordBreak: 'break-all' }}>{agent.wallet_address || '—'}</div>
              </div>
            </div>
          </div>

          {services.length > 0 && (
            <div className="d7-detail-section">
              <div className="d7-detail-label">Services ({services.length})</div>
              <div className="d7-card-grid">
                {services.map(s => (
                  <Link to={`/services/${s.id}`} key={s.id} className="d7-card" style={{ textDecoration: 'none' }}>
                    <div className="d7-card-title">{s.name}</div>
                    <div className="d7-card-desc">{(s.description || '').slice(0, 100)}</div>
                    <div className="d7-card-meta">
                      <span className="d7-card-tag">{s.min_price_agnt}–{s.max_price_agnt} AGNT</span>
                      {s.capabilities?.map(c => <span key={c} className="d7-card-tag">{c}</span>)}
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
