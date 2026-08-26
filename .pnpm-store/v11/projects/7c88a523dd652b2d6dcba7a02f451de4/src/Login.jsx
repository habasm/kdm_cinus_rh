import { useState } from 'react'

const USERNAME = 'admin'
const PASSWORD = '@admin365'

export default function Login({ onSuccess }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')

  const submit = (event) => {
    event.preventDefault()
    if (username.trim() === USERNAME && password === PASSWORD) {
      localStorage.setItem('clinical-authenticated', 'true')
      onSuccess()
      return
    }
    setError('That sign-in did not match. Check your details and try again.')
  }

  return (
    <main className="login-page">
      <div className="login-orbit orbit-one" />
      <div className="login-orbit orbit-two" />
      <section className="login-shell" aria-label="Kidanemihiret clinical system sign in">
        <div className="login-story">
          <div className="login-brand">
            <span className="login-brand-mark">✚</span>
            <span><strong>KIDANEMIHIRET</strong><small>Integrated clinical system</small></span>
          </div>
          <div className="login-story-copy">
            <span className="login-kicker">CARE, CONNECTED</span>
            <h1>A calmer way to run<br /><em>every</em> clinical day.</h1>
            <p>One focused workspace for maternal care, child nutrition and the people behind every record.</p>
          </div>
          <div className="login-signal"><span className="signal-dot" /><span>Facility workspace ready</span><b>24/7</b></div>
        </div>

        <div className="login-card-wrap">
          <div className="login-card">
            <div className="login-card-top"><span className="pulse-icon">⌁</span><span>SECURE ACCESS</span></div>
            <h2>Welcome back</h2>
            <p className="login-subtitle">Sign in to continue your clinical workspace.</p>
            <form onSubmit={submit}>
              <label className="login-field"><span>Username</span><div className="login-input"><span className="input-icon">◎</span><input value={username} onChange={(e) => { setUsername(e.target.value); setError('') }} autoComplete="username" placeholder="Enter your username" required /></div></label>
              <label className="login-field"><span>Password</span><div className="login-input"><span className="input-icon">⌑</span><input type={showPassword ? 'text' : 'password'} value={password} onChange={(e) => { setPassword(e.target.value); setError('') }} autoComplete="current-password" placeholder="Enter your password" required /><button type="button" className="password-toggle" onClick={() => setShowPassword(!showPassword)} aria-label={showPassword ? 'Hide password' : 'Show password'}>{showPassword ? 'Hide' : 'Show'}</button></div></label>
              {error && <p className="login-error" role="alert">{error}</p>}
              <button className="login-submit" type="submit"><span>Enter workspace</span><b>↗</b></button>
            </form>
            <div className="login-note"><span>⌁</span><p>Protected clinical information<br /><small>Your session is private and encrypted.</small></p></div>
          </div>
          <div className="login-card-footer"><span>AMHARA · BAHIR DAR</span><span>v2.4</span></div>
        </div>
      </section>
    </main>
  )
}
