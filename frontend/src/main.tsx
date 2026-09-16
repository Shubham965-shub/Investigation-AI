import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './tailwind.css'
import App from './App.tsx'
import { initPosthog } from './telemetry/posthog'

initPosthog()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
