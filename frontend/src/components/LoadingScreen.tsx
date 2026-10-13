import React from 'react'

const LoadingScreen: React.FC = () => {
  return (
    <div className="flex flex-col items-center justify-center min-h-[400px]">
      <div className="relative">
        {/* Animated Nexus logo */}
        <div className="relative w-24 h-24">
          <div className="absolute inset-0 rounded-full border-4 border-nexus-200 dark:border-nexus-800 border-t-nexus-600 dark:border-t-nexus-400 animate-spin"></div>
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-12 h-12 bg-gradient-to-br from-nexus-500 to-nexus-700 rounded-full flex items-center justify-center">
              <svg className="w-6 h-6 text-white animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
          </div>
        </div>
        
        {/* Pulsing dots */}
        <div className="flex justify-center gap-2 mt-8">
          <div className="w-2 h-2 bg-nexus-500 rounded-full animate-pulse" style={{ animationDelay: '0ms' }}></div>
          <div className="w-2 h-2 bg-nexus-500 rounded-full animate-pulse" style={{ animationDelay: '300ms' }}></div>
          <div className="w-2 h-2 bg-nexus-500 rounded-full animate-pulse" style={{ animationDelay: '600ms' }}></div>
        </div>
      </div>
      
      <p className="mt-6 text-lg font-medium text-gray-700 dark:text-gray-300">
        Cargando NEXUS AI...
      </p>
      <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
        Inicializando plataforma multi-IA
      </p>
    </div>
  )
}

export default LoadingScreen