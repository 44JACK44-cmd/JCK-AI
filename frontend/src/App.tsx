import React, { Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useTheme } from './contexts/ThemeContext'
import { useSocket } from './hooks/useSocket'
import Layout from './components/Layout'
import LoadingScreen from './components/LoadingScreen'
import HealthCheck from './components/HealthCheck'

// Lazy load pages for better performance
const Dashboard = React.lazy(() => import('./pages/Dashboard'))
const Providers = React.lazy(() => import('./pages/Providers'))
const Conversations = React.lazy(() => import('./pages/Conversations'))
const Brain = React.lazy(() => import('./pages/Brain'))
const Projects = React.lazy(() => import('./pages/Projects'))
const Settings = React.lazy(() => import('./pages/Settings'))
const Agent = React.lazy(() => import('./pages/Agent'))

function App() {
  const { theme } = useTheme()
  
  // Real-time updates arrive via SSE (useEventStream); keep hook for connection state consumers
  useSocket()
  
  // Set theme class on document
  React.useEffect(() => {
    document.documentElement.className = theme
  }, [theme])

  return (
    <div className={`min-h-screen bg-gray-50 dark:bg-gray-900 transition-colors duration-200 ${theme}`}>
      {/* Health check */}
      <HealthCheck />
      
      {/* Main layout */}
      <Layout>
        <Suspense fallback={<LoadingScreen />}>
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/providers" element={<Providers />} />
            <Route path="/conversations" element={<Conversations />} />
            <Route path="/brain" element={<Brain />} />
            <Route path="/projects" element={<Projects />} />
            <Route path="/agent" element={<Agent />} />
            <Route path="/settings" element={<Settings />} />
            
            {/* 404 route */}
            <Route path="*" element={
              <div className="flex flex-col items-center justify-center h-[60vh]">
                <div className="text-center">
                  <h1 className="text-6xl font-bold gradient-text mb-4">404</h1>
                  <p className="text-xl text-gray-600 dark:text-gray-400 mb-8">
                    Página no encontrada
                  </p>
                  <a href="/dashboard" className="btn-primary">
                    Volver al inicio
                  </a>
                </div>
              </div>
            } />
          </Routes>
        </Suspense>
      </Layout>
    </div>
  )
}

export default App