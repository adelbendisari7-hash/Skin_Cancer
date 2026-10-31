import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Coque } from './components/Coque'
import { Chargement, Message } from './components/ui'
import { FournisseurApp, useApp } from './contexte'
import { FournisseurLangue } from './components/Langue'
import { t } from './i18n'
import { Connexion, Installation } from './pages/Acces'
import { Accueil } from './pages/Accueil'
import { Administration, Compte } from './pages/Administration'
import { AnalyseDetail } from './pages/AnalyseDetail'
import { LesionDetail } from './pages/LesionDetail'
import { Modele } from './pages/Modele'
import { NouvelleAnalyse } from './pages/NouvelleAnalyse'
import { Analyses, PatientDetail, Patients } from './pages/Patients'

function Routage() {
  const { etat, utilisateur, chargement, erreur } = useApp()
  if (chargement) return <div className="px-10"><Chargement texte={t('commun.demarrage')} /></div>
  if (erreur || !etat) return <div className="mx-auto max-w-xl p-10"><Message>{erreur ?? t('commun.serveurInjoignable')}</Message></div>
  if (etat.installation_requise) {
    return <Routes><Route path="*" element={<Installation />} /></Routes>
  }
  if (!utilisateur) {
    return <Routes><Route path="/connexion" element={<Connexion />} /><Route path="*" element={<Navigate to="/connexion" replace />} /></Routes>
  }
  return (
    <Routes>
      <Route element={<Coque />}>
        <Route index element={<Accueil />} />
        <Route path="analyses" element={<Analyses />} />
        <Route path="analyses/nouvelle" element={<NouvelleAnalyse />} />
        <Route path="analyses/:id" element={<AnalyseDetail />} />
        <Route path="patients" element={<Patients />} />
        <Route path="patients/:id" element={<PatientDetail />} />
        <Route path="lesions/:id" element={<LesionDetail />} />
        <Route path="modele" element={<Modele />} />
        <Route path="compte" element={<Compte />} />
        {utilisateur.role === 'admin' && <Route path="administration" element={<Administration />} />}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <FournisseurLangue>
      <BrowserRouter>
        <FournisseurApp><Routage /></FournisseurApp>
      </BrowserRouter>
    </FournisseurLangue>
  )
}
