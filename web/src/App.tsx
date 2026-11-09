import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom'
import { DemandPage } from './pages/DemandPage'
import { GamePage } from './pages/GamePage'
import { LabPage } from './pages/LabPage'
import { PlannerPage } from './pages/PlannerPage'
import { RevealPage } from './pages/RevealPage'

export default function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <header className="topbar">
          <div className="brand">RoRo Yield Optimizer</div>
          <nav aria-label="Main">
            <NavLink to="/" end>Planner</NavLink>
            <NavLink to="/game">Game</NavLink>
            <NavLink to="/lab">Lab</NavLink>
            <NavLink to="/demand">Demand levels</NavLink>
          </nav>
        </header>
        <main>
          <Routes>
            <Route path="/" element={<PlannerPage />} />
            <Route path="/game" element={<GamePage />} />
            <Route path="/reveal" element={<RevealPage />} />
            <Route path="/lab" element={<LabPage />} />
            <Route path="/demand" element={<DemandPage />} />
          </Routes>
        </main>
        <footer>Synthetic data, not DFDS data. A planning estimate, not a loading computer.</footer>
      </div>
    </BrowserRouter>
  )
}
