import { Eye, EyeOff, HardDrive, ShieldCheck, Stethoscope } from 'lucide-react'
import { useState, type FormEvent, type KeyboardEvent, type ReactNode } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { Signe } from '../components/Coque'
import { ChoixLangue } from '../components/Langue'
import { Bouton, Champ, Message, Saisie } from '../components/ui'
import { useApp } from '../contexte'
import { DEMO } from '../demoStatique'
import { t } from '../i18n'
import { statutModele } from '../lib/format'

// Trame millimétrée discrète (papier de tracés médicaux) : traits fins tous les 8 px, renforcés tous les 40 px.
const TRAME = {
  backgroundImage: [
    'linear-gradient(rgba(255,255,255,.045) 1px, transparent 1px)', 'linear-gradient(90deg, rgba(255,255,255,.045) 1px, transparent 1px)',
    'linear-gradient(rgba(255,255,255,.018) 1px, transparent 1px)', 'linear-gradient(90deg, rgba(255,255,255,.018) 1px, transparent 1px)',
  ].join(','),
  backgroundSize: '40px 40px, 40px 40px, 8px 8px, 8px 8px',
}

const ENGAGEMENTS = [
  { icone: Stethoscope, titre: 'acces.engagement1Titre', texte: 'acces.engagement1Texte' },
  { icone: ShieldCheck, titre: 'acces.engagement2Titre', texte: 'acces.engagement2Texte' },
  { icone: HardDrive, titre: 'acces.engagement3Titre', texte: 'acces.engagement3Texte' },
] as const

/** Panneau de présentation (écrans larges) : ce que fait l'outil et ce qu'il garantit, dans une ambiance clinique. */
function Presentation({ produit }: { produit?: string }) {
  return (
    <aside className="relative hidden flex-col overflow-hidden bg-gradient-to-b from-[#0f5f5a] via-[#0b4d49] to-[#083d3a] text-white lg:flex">
      <div className="pointer-events-none absolute inset-0" style={TRAME} aria-hidden />
      {/* rappel discret du champ du dermoscope : anneaux et graduations au trait, dans l'angle */}
      <svg viewBox="-400 -400 800 800" className="pointer-events-none absolute -end-72 -bottom-72 size-[640px] opacity-[0.1]" aria-hidden>
        {[150, 230, 310].map((r) => <circle key={r} r={r} fill="none" stroke="#fff" strokeWidth="1.5" />)}
        {Array.from({ length: 120 }, (_, k) => {
          const a = (k * 3 * Math.PI) / 180, long = k % 10 === 0
          return <line key={k} x1={310 * Math.cos(a)} y1={310 * Math.sin(a)} x2={(long ? 348 : 328) * Math.cos(a)}
            y2={(long ? 348 : 328) * Math.sin(a)} stroke="#fff" strokeWidth={long ? 2 : 1.2} />
        })}
      </svg>

      <div className="relative flex items-center gap-3 px-14 pt-11">
        <Signe taille={32} />
        <span className="text-[18px] font-bold">{produit}</span>
      </div>

      <div className="relative my-auto max-w-[560px] px-14 py-10">
        <h2 className="text-[34px] leading-[1.15] font-bold text-white text-balance">{t('acces.panneauTitre')}</h2>
        <p className="mt-4 text-[16px] leading-relaxed text-white/80">{t('acces.panneauTexte')}</p>
        <ul className="mt-10 flex flex-col gap-6">
          {ENGAGEMENTS.map(({ icone: I, titre, texte }) => (
            <li key={titre} className="flex gap-4">
              <span className="grid size-10 shrink-0 place-items-center rounded-full bg-white/10 ring-1 ring-white/20">
                <I className="size-5" aria-hidden />
              </span>
              <div>
                <p className="text-[15.5px] font-semibold">{t(titre)}</p>
                <p className="mt-0.5 text-[14.5px] leading-relaxed text-white/75">{t(texte)}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>

      <p className="relative max-w-[560px] px-14 pb-10 text-[13px] leading-relaxed text-white/60">{t('acces.panneauMention')}</p>
    </aside>
  )
}

/** Écrans d'accès : à gauche la présentation de l'outil, à droite le formulaire. */
function Cadre({ titre, intro, children }: { titre: string; intro: ReactNode; children: ReactNode }) {
  const { etat } = useApp()
  const etablissement = etat && !etat.installation_requise ? etat.etablissement : ''
  return (
    <div className="grid min-h-dvh lg:grid-cols-[minmax(0,1.1fr)_minmax(460px,1fr)]">
      <Presentation produit={etat?.produit} />

      <main className="flex flex-col px-6 py-6 sm:px-12 sm:py-8">
        <div className="flex items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-2.5">
            <span className="lg:hidden"><Signe taille={30} /></span>
            <div className="min-w-0 leading-tight">
              <p className="truncate text-[15px] font-bold lg:hidden">{etat?.produit}</p>
              {etablissement && <p className="truncate text-[14px] text-encre-2">{etablissement}</p>}
            </div>
          </div>
          <ChoixLangue className="shrink-0" />
        </div>

        <div className="mx-auto my-auto w-full max-w-[400px] py-10">
          <h1 className="text-[30px] leading-tight font-bold">{titre}</h1>
          <div className="mt-2 mb-8 text-[15px] text-encre-2">{intro}</div>
          {children}
        </div>

        <footer className="text-[12.5px] leading-relaxed text-encre-3">
          <p>{t('acces.version', { produit: etat?.produit ?? '', v: etat?.version ?? '' })}</p>
          {etat?.modele.charge && <p>{statutModele(etat.modele.statut, etat.modele.statut_i18n)}</p>}
          {DEMO && <p>{t('demo.attribution')}</p>}
        </footer>
      </main>
    </div>
  )
}

/** Mot de passe avec bouton afficher / masquer et alerte « majuscules verrouillées ». */
function MotDePasse({ id, value, onChange, autoComplete, minLength }: {
  id: string; value: string; onChange: (v: string) => void; autoComplete: string; minLength?: number
}) {
  const [visible, setVisible] = useState(false)
  const [majuscules, setMajuscules] = useState(false)
  const verifier = (e: KeyboardEvent<HTMLInputElement>) => setMajuscules(e.getModifierState('CapsLock'))
  return (
    <>
      <div className="relative">
        <Saisie id={id} type={visible ? 'text' : 'password'} autoComplete={autoComplete} value={value} required
          minLength={minLength} onChange={(e) => onChange(e.target.value)} onKeyDown={verifier} onKeyUp={verifier}
          onBlur={() => setMajuscules(false)} className="h-11 pe-11" />
        <button type="button" onClick={() => setVisible(!visible)} aria-pressed={visible} aria-controls={id}
          aria-label={visible ? t('acces.masquerMdp') : t('acces.afficherMdp')} title={visible ? t('acces.masquerMdp') : t('acces.afficherMdp')}
          className="absolute end-1.5 top-1/2 grid size-8 -translate-y-1/2 place-items-center rounded-[4px] text-encre-2 hover:bg-trait-2 hover:text-encre">
          {visible ? <EyeOff className="size-[18px]" aria-hidden /> : <Eye className="size-[18px]" aria-hidden />}
        </button>
      </div>
      {majuscules && <p className="text-[13px] font-semibold text-avis" role="status">{t('acces.majuscules')}</p>}
    </>
  )
}

export function Connexion() {
  const { definirUtilisateur } = useApp()
  const naviguer = useNavigate()
  const restauree = useSearchParams()[0].has('restauree')
  const [identifiant, setIdentifiant] = useState(DEMO ? 'admin' : '')
  const [mdp, setMdp] = useState(DEMO ? 'demonstration' : '')
  const [erreur, setErreur] = useState<string | null>(null)
  const [envoi, setEnvoi] = useState(false)

  async function envoyer(e: FormEvent) {
    e.preventDefault()
    setEnvoi(true); setErreur(null)
    try {
      definirUtilisateur(await api.connexion(identifiant, mdp))
      naviguer('/')
    } catch (err) {
      setErreur((err as Error).message)
    } finally {
      setEnvoi(false)
    }
  }

  return (
    <Cadre titre={t('acces.connexion')} intro={t('acces.connexionIntro')}>
      <form onSubmit={envoyer} className="flex flex-col gap-5">
        {DEMO && <Message type="info">{t('demo.connexion')}</Message>}
        {restauree && !erreur && <Message type="info">{t('acces.restauree')}</Message>}
        {erreur && <Message>{erreur}</Message>}
        <Champ label={t('acces.identifiant')}>
          {(id) => <Saisie id={id} autoComplete="username" value={identifiant} onChange={(e) => setIdentifiant(e.target.value)}
            required autoFocus spellCheck={false} autoCapitalize="none" className="h-11" />}
        </Champ>
        <Champ label={t('acces.motDePasse')}>
          {(id) => <MotDePasse id={id} value={mdp} onChange={setMdp} autoComplete="current-password" />}
        </Champ>
        <Bouton type="submit" chargement={envoi} className="mt-1 h-11 w-full text-[15px]">{t('acces.seConnecter')}</Bouton>
        {!DEMO && <p className="text-[13.5px] leading-relaxed text-encre-2">{t('acces.oubli')}</p>}
      </form>
    </Cadre>
  )
}

export function Installation() {
  const { rafraichir } = useApp()
  const naviguer = useNavigate()
  const [f, setF] = useState({ nom_etablissement: '', nom_complet: '', identifiant: '', mot_de_passe: '', confirmation: '' })
  const [erreur, setErreur] = useState<string | null>(null)
  const [envoi, setEnvoi] = useState(false)
  const maj = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })

  async function envoyer(e: FormEvent) {
    e.preventDefault()
    if (f.mot_de_passe !== f.confirmation) { setErreur(t('acces.mdpDifferents')); return }
    setEnvoi(true); setErreur(null)
    try {
      const { confirmation: _, ...donnees } = f
      void _
      await api.installer(donnees)
      await rafraichir()
      naviguer('/')
    } catch (err) {
      setErreur((err as Error).message)
    } finally {
      setEnvoi(false)
    }
  }

  return (
    <Cadre titre={t('acces.installation')} intro={t('acces.installationIntro')}>
      <form onSubmit={envoyer} className="flex flex-col gap-5">
        {erreur && <Message>{erreur}</Message>}
        <Champ label={t('acces.nomEtablissement')} aide={t('acces.nomEtablissementAide')}>
          {(id) => <Saisie id={id} value={f.nom_etablissement} onChange={maj('nom_etablissement')} required minLength={2} autoFocus className="h-11" />}
        </Champ>
        <Champ label={t('acces.votreNom')}>{(id) => <Saisie id={id} value={f.nom_complet} onChange={maj('nom_complet')} placeholder="Dr Amina Benali" required minLength={2} className="h-11" />}</Champ>
        <Champ label={t('acces.identifiantConnexion')} aide={t('acces.identifiantAide')}>
          {(id) => <Saisie id={id} value={f.identifiant} onChange={maj('identifiant')} autoComplete="username" required
            pattern="[A-Za-z0-9._\-]{3,64}" spellCheck={false} autoCapitalize="none" className="h-11" />}
        </Champ>
        <Champ label={t('acces.motDePasse')} aide={t('acces.mdpAide')}>
          {(id) => <MotDePasse id={id} value={f.mot_de_passe} onChange={(v) => setF({ ...f, mot_de_passe: v })} autoComplete="new-password" minLength={10} />}
        </Champ>
        <Champ label={t('acces.confirmerMdp')}>
          {(id) => <MotDePasse id={id} value={f.confirmation} onChange={(v) => setF({ ...f, confirmation: v })} autoComplete="new-password" />}
        </Champ>
        <Bouton type="submit" chargement={envoi} className="mt-1 h-11 w-full text-[15px]">{t('acces.creerAdmin')}</Bouton>
      </form>
    </Cadre>
  )
}
