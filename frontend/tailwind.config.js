/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Custom dark mode colors
        dark: {
          bg: '#0f172a',      // slate-900
          card: '#1e293b',    // slate-800
          border: '#334155',  // slate-700
          text: '#e2e8f0',    // slate-200
          muted: '#94a3b8',   // slate-400
        },
      },
    },
  },
  plugins: [],
}
