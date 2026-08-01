/** Left navigation rail with the profile switcher. */

import { NavLink } from 'react-router-dom'
import { useApp } from './AppProvider'

const ICONS = {
  dashboard: 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
  drill: 'M12 3a9 9 0 100 18 9 9 0 000-18zm0 5a4 4 0 100 8 4 4 0 000-8z',
  exam: 'M12 3a9 9 0 100 18 9 9 0 000-18zM12 7v5l3.5 2',
  games: 'M13 2L4 14h6l-1 8 9-12h-6l1-8z',
  rules: 'M12 3a9 9 0 100 18 9 9 0 000-18zM15.5 8.5l-2 5-5 2 2-5 5-2z',
  bank: 'M12 3l9 5-9 5-9-5 9-5zM3 13l9 5 9-5M3 17l9 5 9-5',
  cases: 'M6 3v6a3 3 0 003 3h6a3 3 0 013 3v6M6 3H4m2 0h2M18 21h-2m2 0h2M6 12h12',
  calibration: 'M3 20h18M6 20V10m6 10V5m6 15v-7',
  detection: 'M12 3a9 9 0 100 18 9 9 0 000-18zm0 4v5m0 3v.01',
} as const

const LINKS: { to: string; key: keyof typeof ICONS; label: string }[] = [
  { to: '/', key: 'dashboard', label: 'Dashboard' },
  { to: '/drill', key: 'drill', label: 'Drill' },
  { to: '/exam', key: 'exam', label: 'Mock exam' },
  { to: '/cases', key: 'cases', label: 'Cases' },
  { to: '/games', key: 'games', label: 'Short form' },
  { to: '/rules', key: 'rules', label: 'Decision rules' },
  { to: '/calibration', key: 'calibration', label: 'Calibration' },
  { to: '/detection', key: 'detection', label: 'Detection' },
  { to: '/bank', key: 'bank', label: 'Question bank' },
]

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"
         strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  )
}

export function Rail() {
  const { boot, profile, switchProfile } = useApp()

  const names = [...boot.profiles]
  if (profile && !names.includes(profile)) names.push(profile)

  return (
    <aside className="rail">
      <div className="brand">
        <svg viewBox="0 0 32 32" aria-hidden="true">
          <rect width="32" height="32" rx="7" fill="#0e1419" />
          <path d="M9 17l4.5 4.5L23 12" stroke="var(--accent)" strokeWidth="3" fill="none"
                strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <div>
          <strong>{boot.cert}</strong>
          <span>{boot.questions} questions</span>
        </div>
      </div>

      <nav className="nav" aria-label="Main">
        {LINKS.map((l) => (
          <NavLink key={l.to} to={l.to} end={l.to === '/'}
                   className={({ isActive }) => (isActive ? 'active' : '')}>
            <Icon d={ICONS[l.key]} />
            {l.label}
          </NavLink>
        ))}
      </nav>

      <div className="rail-foot">
        <label htmlFor="profile-select">Studying as</label>
        <div className="profile-row">
          <select
            id="profile-select"
            value={profile}
            onChange={(e) => switchProfile(e.target.value)}
          >
            <option value="">Shared (default)</option>
            {names.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
          <button
            className="icon-btn"
            title="Add a profile"
            aria-label="Add a profile"
            onClick={() => {
              const name = window.prompt('Name for the new study profile (e.g. a first name):')
              if (name && name.trim()) switchProfile(name.trim())
            }}
          >
            +
          </button>
        </div>
        <p className="rail-note">
          Results are kept separate per person. The question bank is shared.
        </p>
      </div>
    </aside>
  )
}
