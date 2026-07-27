/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        darkBg: '#090d16',
        cardBg: '#111827',
        borderSlate: '#1e293b',
        accentBlue: '#3b82f6',
        accentPurple: '#8b5cf6',
        textSilver: '#cbd5e1'
      }
    },
  },
  plugins: [],
}