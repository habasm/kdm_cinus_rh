import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './Shell'
import Login from './Login'
import './styles.css'
import './tabs.css'

function Root() {
  const [authenticated, setAuthenticated] = React.useState(() => localStorage.getItem('clinical-authenticated') === 'true')
  const [user, setUser] = React.useState(() => { try { return JSON.parse(localStorage.getItem('clinical-user') || 'null') } catch { return null } })
  return authenticated ? <App user={user} /> : <Login onSuccess={(nextUser) => { setUser(nextUser); setAuthenticated(true) }} />
}

createRoot(document.getElementById('root')).render(<React.StrictMode><Root /></React.StrictMode>)
