import { ClipboardCheck, Cpu, KeyRound, LayoutList, LogOut, ScanSearch, Settings, Users } from 'lucide-react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useApp } from '../contexte'
import { DEMO } from '../demoStatique'
import { t, type Cle } from '../i18n'
import { ChoixLangue } from './Langue'

const LIENS: { vers: string; libelle: Cle; icone: typeof Cpu; fin?: boolean }[] = [
  { vers: '/', libelle: 'nav.fileTravail', icone: LayoutList, fin: true },
  { vers: '/analyses/nouvelle', libelle: 'nav.nouvelleAnalyse', icone: ScanSearch },
  { vers: '/patients', libelle: 'nav.patients', icone: Users },
  { vers: '/analyses', libelle: 'nav.analyses', icone: ClipboardCheck, fin: true },
  { vers: '/modele', libelle: 'nav.modele', icone: Cpu },
]

/** Petit oculaire servant de signe distinctif du produit. */
export function Signe({ taille = 26 }: { taille?: number }) {
  return (
    <svg width={taille} height={taille} viewBox="-14 -14 28 28" aria-hidden>
      <circle r="13" fill="var(--color-derme)" />
      {Array.from({ length: 24 }, (_, i) => {
        const a = (i * 15 * Math.PI) / 180
        return <line key={i} x1={10.4 * Math.cos(a)} y1={10.4 * Math.sin(a)} x2={(i % 6 ? 11.6 : 12.6) * Math.cos(a)}
          y2={(i % 6 ? 11.6 : 12.6) * Math.sin(a)} stroke="var(--color-encre)" strokeOpacity=".5" strokeWidth=".6" />
      })}
      <circle r="9.6" fill="var(--color-encre)" />
      <ellipse cx="0.8" cy="0.4" rx="4.6" ry="3.8" fill="#7a4a35" />
      <ellipse cx="1.4" cy="0.8" rx="2.2" ry="1.7" fill="#3b2219" />
    </svg>
  )
}

export function Coque() {
  const { etat, utilisateur, deconnecter } = useApp()
  const naviguer = useNavigate()
  const demo = etat?.modele.statut?.startsWith('DÉMONSTRATION')
  const lien = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 rounded-[5px] px-3 py-2 text-[14px] font-semibold transition-colors ${isActive
      ? 'bg-bloc-pale text-bloc-fonce' : 'text-encre-2 hover:bg-trait-2 hover:text-encre'}`

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[236px_1fr]">
      <aside className="border-b border-trait bg-surface lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col lg:border-e lg:border-b-0">
        <div className="flex items-center gap-2.5 px-5 pt-5 pb-4">
          <Signe />
          <div className="min-w-0">
            <p className="truncate text-[16px] font-semibold leading-tight">{etat?.produit}</p>
            <p className="truncate text-[12px] text-encre-2">{etat?.etablissement}</p>
          </div>
        </div>
        <nav aria-label={t('nav.principale')} className="flex gap-1 overflow-x-auto px-3 pb-3 lg:flex-1 lg:flex-col lg:overflow-visible">
          {LIENS.map(({ vers, libelle, icone: I, fin }) => (
            <NavLink key={vers} to={vers} end={fin} className={lien}>
              <I className="size-[18px] shrink-0" aria-hidden /> <span className="whitespace-nowrap">{t(libelle)}</span>
            </NavLink>
          ))}
          {utilisateur?.role === 'admin' && (
            <NavLink to="/administration" className={lien}>
              <Settings className="size-[18px] shrink-0" aria-hidden /> <span className="whitespace-nowrap">{t('nav.administration')}</span>
            </NavLink>
          )}
          <NavLink to="/compte" className={(s) => `${lien(s)} lg:hidden`}>
            <KeyRound className="size-[18px] shrink-0" aria-hidden /> <span className="whitespace-nowrap">{t('nav.monCompte')}</span>
          </NavLink>
          <ChoixLangue className="shrink-0 self-center lg:hidden" />
          <button onClick={async () => { await deconnecter(); naviguer('/connexion') }}
            className="flex items-center gap-3 rounded-[5px] px-3 py-2 text-[14px] font-semibold whitespace-nowrap text-encre-2 hover:bg-trait-2 lg:hidden">
            <LogOut className="size-[18px] shrink-0" aria-hidden /> {t('nav.deconnecter')}
          </button>
        </nav>
        <div className="hidden border-t border-trait-2 px-3 py-3 lg:block">
          <div className="px-3 pb-2">
            <p className="truncate text-[14px] font-semibold">{utilisateur?.nom_complet}</p>
            <p className="text-[12px] text-encre-2">{utilisateur?.role === 'admin' ? t('role.admin') : t('role.medecin')}</p>
          </div>
          <NavLink to="/compte" className={lien}><KeyRound className="size-[18px]" aria-hidden /> {t('nav.monCompte')}</NavLink>
          <button onClick={async () => { await deconnecter(); naviguer('/connexion') }}
            className="flex w-full items-center gap-3 rounded-[5px] px-3 py-2 text-[14px] font-semibold text-encre-2 hover:bg-trait-2 hover:text-encre">
            <LogOut className="size-[18px]" aria-hidden /> {t('nav.deconnecter')}
          </button>
          <ChoixLangue className="mt-3 ms-3" />
        </div>
      </aside>
      <div className="min-w-0">
        {demo && (
          <div className="border-b border-renvoi/15 bg-renvoi-pale px-6 py-2 text-[13px] text-renvoi lg:px-10">
            {t('bandeau.demo')}
            {DEMO && <p className="mt-0.5 font-semibold">{t('demo.bandeau')} {t('demo.attribution')}</p>}
          </div>
        )}
        {!etat?.modele.charge && (
          <div className="border-b border-urgent/20 bg-urgent-pale px-6 py-2 text-[13px] text-urgent lg:px-10">
            {t('bandeau.moteurIndispo', { raison: etat?.modele.erreur ?? t('bandeau.chargementEnCours') })}
          </div>
        )}
        <main className="mx-auto max-w-[1180px] px-5 py-8 lg:px-10">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
