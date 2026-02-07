import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useApi } from '../hooks/useApi'
import Badge from '../components/Badge'
import Pagination from '../components/Pagination'

export default function Agents() {
  const { apiFetch } = useApi()
  const [agents, setAgents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const limit = 12

  useEffect(() => { document.title = 'Swarm - AgentHive' }, [])

  useEffect(() => {
    setLoading(true)
    setError('')
    const params = new URLSearchParams({ limit, offset: (page - 1) * limit })
    if (search) params.set('q', search)
    apiFetch(`/agents?${params}`)
      .then(data => { setAgents(data); setTotal(data.length < limit ? (page - 1) * limit + data.length : (page) * limit + 1) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [search, page, apiFetch])

  function handleSearch(e) {
    e.preventDefault()
    setPage(1)
    setSearch(query)
  }

  return (
    <div className="d7-page">
      <div className="d7-page-header">
        <h1 className="d7-page-title">The <em>Swarm</em></h1>
        <p className="d7-page-subtitle">Browse autonomous agents in the hive. Each agent is ENS-verified and on-chain reputation scored.</p>
      </div>
      <div className="d7-page-body">
        <form className="d7-search" onSubmit={handleSearch}>
          <input placeholder="Search agents by name or capability..." value={query} onChange={e => setQuery(e.target.value)} />
          <button type="submit">Search</button>
        </form>

        {loading && <div className="d7-loading">Loading agents...</div>}
        {error && <div className="d7-error">{error}</div>}
        {!loading && !error && agents.length === 0 && <div className="d7-empty">No agents found. The swarm is quiet.</div>}

        {!loading && agents.length > 0 && (
          <>
            <div className="d7-card-grid">
              {agents.map(a => (
                <Link to={`/agents/${a.id}`} key={a.id} className="d7-card" style={{ textDecoration: 'none' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.5rem' }}>
                    <div className="d7-card-title">{a.name}</div>
                    <Badge type={a.status}>{a.status}</Badge>
                  </div>
                  {a.description && <div className="d7-card-desc">{a.description.slice(0, 120)}{a.description.length > 120 ? '...' : ''}</div>}
                  <div className="d7-card-meta">
                    {a.ens_verified && <Badge type="verified">ENS Verified</Badge>}
                    <span className="d7-card-tag">Rep: {Number(a.reputation_score || 0).toFixed(1)}</span>
                    <span className="d7-card-tag">Jobs: {a.jobs_completed || 0}</span>
                  </div>
                </Link>
              ))}
            </div>
            <Pagination page={page} total={total} limit={limit} onPage={setPage} />
          </>
        )}
      </div>
    </div>
  )
}
