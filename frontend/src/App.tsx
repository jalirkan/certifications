/**
 * Routes.
 *
 * Hash routing on purpose: serve.py serves static files and 404s unknown paths,
 * so a history-API route would break on reload. The old front end used hashes
 * too, which keeps any bookmarks working.
 */

import { HashRouter, Route, Routes } from 'react-router-dom'
import { AppProvider } from './app/AppProvider'
import { Rail } from './app/Rail'
import { Dashboard } from './screens/Dashboard'
import { DrillSetup, DrillRunner } from './screens/Drill'
import { ExamHome, ExamRunner, ExamResultScreen } from './screens/Exam'
import { GamesHome, ColdRead, Autopsy } from './screens/Games'
import { Rules, StudyCard } from './screens/Rules'
import { Bank } from './screens/Bank'

export default function App() {
  return (
    <HashRouter>
      <AppProvider>
        <a className="skip-link" href="#main">Skip to content</a>
        <Rail />
        <main className="main" id="main" tabIndex={-1}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/drill" element={<DrillSetup />} />
            <Route path="/drill/run" element={<DrillRunner />} />
            <Route path="/exam" element={<ExamHome />} />
            <Route path="/exam/run/:id" element={<ExamRunner />} />
            <Route path="/exam/result/:id" element={<ExamResultScreen />} />
            <Route path="/games" element={<GamesHome />} />
            <Route path="/games/coldread" element={<ColdRead />} />
            <Route path="/games/autopsy" element={<Autopsy />} />
            <Route path="/rules" element={<Rules />} />
            <Route path="/rules/card" element={<StudyCard />} />
            <Route path="/bank" element={<Bank />} />
            <Route path="*" element={<Dashboard />} />
          </Routes>
        </main>
      </AppProvider>
    </HashRouter>
  )
}
