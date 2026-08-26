import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './Shell'
import Login from './Login'
import './styles.css'
import './tabs.css'

function Root() {
  const [authenticated, setAuthenticated] = React.useState(() => localStorage.getItem('clinical-authenticated') === 'true')
  return authenticated ? <App /> : <Login onSuccess={() => setAuthenticated(true)} />
}

createRoot(document.getElementById('root')).render(<React.StrictMode><Root /></React.StrictMode>)
