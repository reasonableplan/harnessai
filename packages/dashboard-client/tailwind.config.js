/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        wood: {
          light: '#DEB887',
          DEFAULT: '#A0522D',
          dark: '#8B6914',
          floor: '#C4944A',
          wall: '#B8860B',
        },
        agent: {
          director: '#FFD700',
          git: '#F05032',
          frontend: '#61DAFB',
          backend: '#68A063',
          docs: '#F7DF1E',
        },
      },
      fontFamily: {
        pixel: ['"Press Start 2P"', 'monospace'],
      },
      animation: {
        typing: 'typing 0.4s ease-in-out infinite alternate',
        breathing: 'breathing 3s ease-in-out infinite',
        walking: 'walking 0.5s steps(2) infinite',
        blink: 'blink 3s ease-in-out infinite',
        float: 'float 2s ease-in-out infinite',
        steam: 'steam 2s ease-out infinite',
        glow: 'glow 2s ease-in-out infinite alternate',
      },
      keyframes: {
        typing: {
          '0%': { transform: 'translateY(0)' },
          '100%': { transform: 'translateY(-2px)' },
        },
        breathing: {
          '0%, 100%': { transform: 'scaleY(1)' },
          '50%': { transform: 'scaleY(1.02)' },
        },
        walking: {
          '0%': { transform: 'translateX(0)' },
          '50%': { transform: 'translateX(2px)' },
          '100%': { transform: 'translateX(0)' },
        },
        blink: {
          '0%, 45%, 55%, 100%': { opacity: '1' },
          '50%': { opacity: '0' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-4px)' },
        },
        steam: {
          '0%': { opacity: '0.6', transform: 'translateY(0) scale(1)' },
          '100%': { opacity: '0', transform: 'translateY(-12px) scale(1.5)' },
        },
        glow: {
          '0%': { opacity: '0.7' },
          '100%': { opacity: '1' },
        },
      },
    },
  },
  plugins: [],
};
