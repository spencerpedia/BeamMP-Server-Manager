/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js}'],
  theme: {
    extend: {
      colors: {
        surface: { 950: '#0b0f17', 900: '#111723', 800: '#182031', 700: '#222c41', 600: '#2e3a54' },
        accent: { 400: '#fb923c', 500: '#f97316', 600: '#ea580c' },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
}
