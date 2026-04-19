/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './**/templates/**/*.html',
    '../accounts/templates/**/*.html',
    '../accounts/**/*.py',
    './pages/**/*.py',
  ],
  // Referenced only from Django widget attrs (not in HTML) — must not be purged.
  safelist: ['forma-input'],
  theme: {
    extend: {
      fontFamily: {
        display: ['"Bebas Neue"', 'sans-serif'],
        body: ['Barlow', 'system-ui', 'sans-serif'],
        serif: ['Fraunces', 'Georgia', 'serif'],
      },
      colors: {
        ink: '#0F0F0F',
        paper: '#F8F7F3',
        surface: '#EFEDE8',
        rule: '#DDDBD4',
        slate: '#3D4A5C',
        muted: 'rgba(15,15,15,0.45)',
        'very-muted': 'rgba(15,15,15,0.22)',
        blue: {
          DEFAULT: '#1A3FCC',
          mid: '#2952E0',
          light: '#EEF1FB',
        },
        danger: '#CC2A1A',
      },
      fontSize: {
        label: ['0.62rem', { letterSpacing: '0.25em', fontWeight: '600' }],
        eyebrow: ['0.7rem', { letterSpacing: '0.2em', fontWeight: '500' }],
        meta: ['0.68rem', { letterSpacing: '0.08em' }],
        chip: ['0.6rem', { letterSpacing: '0.12em', fontWeight: '500' }],
      },
      letterSpacing: {
        'widest-2': '0.25em',
        'widest-3': '0.2em',
        'wide-2': '0.14em',
        'wide-3': '0.12em',
        'wide-4': '0.1em',
        'wide-5': '0.08em',
      },
      lineHeight: {
        display: '0.88',
        heading: '0.92',
        'tight-2': '1.05',
        body: '1.8',
        serif: '1.65',
      },
      spacing: {
        section: '5rem',
        'section-sm': '3.5rem',
        page: '4rem',
      },
    },
  },
  plugins: [],
};
