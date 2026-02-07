import { Link } from 'react-router-dom'

export default function Footer() {
  return (
    <footer className="d7-footer">
      <div className="d7-footer-brand">AgentHive &copy; 2026</div>
      <div className="d7-footer-links">
        <a href="https://github.com/deathflamingo/AgentMarketplaceHackMoney2026" target="_blank" rel="noreferrer">GitHub</a>
        <Link to="/docs">Documentation</Link>
        <Link to="/agents">Swarm</Link>
      </div>
    </footer>
  )
}
