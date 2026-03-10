/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './frontend/index.html',
    './frontend/src/**/*.{js,jsx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
}
