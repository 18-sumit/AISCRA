/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['"DM Mono"', 'monospace'],
        body:    ['"IBM Plex Sans"', 'sans-serif'],
        mono:    ['"JetBrains Mono"', 'monospace'],
      },
      colors: {
        surface: {
          0: '#080c10',
          1: '#0d1117',
          2: '#161b22',
          3: '#21262d',
          4: '#30363d',
        },
        amber: {
          dim:    '#7a4f0a',
          muted:  '#d97706',
          base:   '#f59e0b',
          bright: '#fbbf24',
        },
        risk: {
          critical: '#ef4444',
          high:     '#f97316',
          medium:   '#eab308',
          low:      '#3b82f6',
          watch:    '#6b7280',
          safe:     '#22c55e',
        }
      },
      animation: {
        'pulse-slow':  'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in':     'fadeIn 0.4s ease-out',
        'slide-up':    'slideUp 0.3s ease-out',
      },
      keyframes: {
        fadeIn:  { from: { opacity: 0 },                    to: { opacity: 1 } },
        slideUp: { from: { opacity: 0, transform: 'translateY(8px)' }, to: { opacity: 1, transform: 'translateY(0)' } },
      }
    },
  },
  plugins: [],
}
