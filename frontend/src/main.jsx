import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/global.css'
import './styles/a11y.css'
import { initMotionPreference } from './hooks/useReducedMotion'
import App from './App.jsx'

initMotionPreference()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
