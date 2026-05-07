import { useState } from 'react'
import { ConsultationPage } from './pages/ConsultationPage'
import { LoginPage } from './pages/LoginPage'
import { DashboardPage } from './pages/DashboardPage'

type Page = 'login' | 'dashboard' | 'consultation'

export default function App() {
  const [page, setPage] = useState<Page>('login')
  const [token, setToken] = useState<string | null>(null)

  const handleLogin = (accessToken: string) => {
    setToken(accessToken)
    setPage('dashboard')
  }

  const handleLogout = () => {
    setToken(null)
    setPage('login')
  }

  if (page === 'login') return <LoginPage onLogin={handleLogin} />
  if (page === 'dashboard') return (
    <DashboardPage
      onStartConsultation={() => setPage('consultation')}
      onLogout={handleLogout}
    />
  )
  return <ConsultationPage token={token!} onBack={() => setPage('dashboard')} />
}
