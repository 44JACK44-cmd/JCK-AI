import React from 'react'

interface StatCardProps {
  title: string
  value: string
  change?: string
  icon?: React.ReactNode
  color?: 'blue' | 'green' | 'purple' | 'orange'
  trend?: 'up' | 'down' | 'stable'
}

const colorClasses: Record<string, string> = {
  blue: 'bg-blue-500/10 text-blue-600 dark:text-blue-400',
  green: 'bg-green-500/10 text-green-600 dark:text-green-400',
  purple: 'bg-purple-500/10 text-purple-600 dark:text-purple-400',
  orange: 'bg-orange-500/10 text-orange-600 dark:text-orange-400',
}

const StatCard: React.FC<StatCardProps> = ({ title, value, change, icon, color = 'blue' }) => (
  <div className="glass-panel rounded-xl p-5 flex items-center gap-4">
    {icon && (
      <div className={`p-3 rounded-lg ${colorClasses[color] || colorClasses.blue}`}>
        {icon}
      </div>
    )}
    <div className="min-w-0">
      <div className="text-sm text-gray-500 dark:text-gray-400 truncate">{title}</div>
      <div className="text-2xl font-bold text-gray-900 dark:text-white">{value}</div>
      {change && <div className="text-xs text-gray-500 dark:text-gray-400 truncate">{change}</div>}
    </div>
  </div>
)

export default StatCard
