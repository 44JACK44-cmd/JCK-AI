import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useTheme } from '../contexts/ThemeContext'
import { Brain, MessageSquare, Cpu, Folder, Settings, Sun, Moon, BarChart3, Terminal } from 'lucide-react'

interface NavItem {
  name: string
  href: string
  icon: React.ReactNode
  description: string
}

const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const location = useLocation()
  const { theme, toggleTheme } = useTheme()

  const navigation: NavItem[] = [
    {
      name: 'Dashboard',
      href: '/dashboard',
      icon: <BarChart3 className="w-5 h-5" />,
      description: 'Visión general del sistema'
    },
    {
      name: 'Proveedores IA',
      href: '/providers',
      icon: <Cpu className="w-5 h-5" />,
      description: 'Gestión de modelos y proveedores'
    },
    {
      name: 'Conversaciones',
      href: '/conversations',
      icon: <MessageSquare className="w-5 h-5" />,
      description: 'Chat individual y colaborativo'
    },
    {
      name: 'Cerebro',
      href: '/brain',
      icon: <Brain className="w-5 h-5" />,
      description: 'Visualización en tiempo real'
    },
    {
      name: 'Proyectos',
      href: '/projects',
      icon: <Folder className="w-5 h-5" />,
      description: 'Gestión de proyectos y archivos'
    },
    {
      name: 'Agente Local',
      href: '/agent',
      icon: <Terminal className="w-5 h-5" />,
      description: 'Terminal y herramientas'
    },
    {
      name: 'Configuración',
      href: '/settings',
      icon: <Settings className="w-5 h-5" />,
      description: 'Ajustes del sistema'
    },
  ]

  return (
    <div className="flex h-screen">
      {/* Sidebar */}
      <aside className="hidden lg:flex lg:w-64 flex-col bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700">
        <div className="p-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-nexus-500 to-nexus-700 rounded-lg flex items-center justify-center">
              <Brain className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold gradient-text">NEXUS AI</h1>
              <p className="text-xs text-gray-500 dark:text-gray-400">Plataforma Multi-IA</p>
            </div>
          </div>
        </div>

        <nav className="flex-1 px-4 space-y-1">
          {navigation.map((item) => {
            const isActive = location.pathname === item.href
            return (
              <Link
                key={item.name}
                to={item.href}
                className={`
                  flex items-center gap-3 px-4 py-3 rounded-lg transition-colors group
                  ${isActive
                    ? 'bg-nexus-50 dark:bg-nexus-900/30 text-nexus-700 dark:text-nexus-300 border border-nexus-200 dark:border-nexus-800'
                    : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700/50'
                  }
                `}
                title={item.description}
              >
                <div className={`
                  ${isActive
                    ? 'text-nexus-600 dark:text-nexus-400'
                    : 'text-gray-500 dark:text-gray-400 group-hover:text-nexus-500'
                  }
                `}>
                  {item.icon}
                </div>
                <span className="font-medium">{item.name}</span>
              </Link>
            )
          })}
        </nav>

        <div className="p-4 border-t border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between">
            <button
              onClick={toggleTheme}
              className="flex items-center gap-2 px-3 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
              title={`Cambiar a modo ${theme === 'light' ? 'oscuro' : 'claro'}`}
            >
              {theme === 'light' ? (
                <>
                  <Moon className="w-4 h-4" />
                  <span className="text-sm">Oscuro</span>
                </>
              ) : (
                <>
                  <Sun className="w-4 h-4" />
                  <span className="text-sm">Claro</span>
                </>
              )}
            </button>
            
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
              <span className="text-xs text-gray-500 dark:text-gray-400">Online</span>
            </div>
          </div>
        </div>
      </aside>

      {/* Mobile header */}
      <div className="lg:hidden fixed top-0 left-0 right-0 z-50 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-gradient-to-br from-nexus-500 to-nexus-700 rounded-lg flex items-center justify-center">
              <Brain className="w-4 h-4 text-white" />
            </div>
            <h1 className="text-lg font-bold gradient-text">NEXUS AI</h1>
          </div>
          
          <button
            onClick={toggleTheme}
            className="p-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
          >
            {theme === 'light' ? (
              <Moon className="w-5 h-5" />
            ) : (
              <Sun className="w-5 h-5" />
            )}
          </button>
        </div>
      </div>

      {/* Main content */}
      <main className="flex-1 overflow-auto pt-16 lg:pt-0">
        <div className="max-w-7xl mx-auto p-4 lg:p-6">
          {children}
        </div>
      </main>

      {/* Mobile navigation */}
      <nav className="lg:hidden fixed bottom-0 left-0 right-0 z-50 bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700">
        <div className="flex justify-around py-2">
          {navigation.slice(0, 4).map((item) => {
            const isActive = location.pathname === item.href
            return (
              <Link
                key={item.name}
                to={item.href}
                className={`
                  flex flex-col items-center p-2 rounded-lg transition-colors
                  ${isActive
                    ? 'text-nexus-600 dark:text-nexus-400'
                    : 'text-gray-500 dark:text-gray-400'
                  }
                `}
              >
                {item.icon}
                <span className="text-xs mt-1">{item.name}</span>
              </Link>
            )
          })}
        </div>
      </nav>
    </div>
  )
}

export default Layout