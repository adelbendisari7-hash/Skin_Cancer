import { FileDown, History, ScanSearch } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api, type Analyse, type EtSiReponse } from '../api'
import { EtSi } from '../components/EtSi'
import { DEMO, pdfDisponible } from '../demoStatique'
import { Avertissements, CriteresABCD, Oculaire, PanneauEvolution, Probabilites, Statut } from '../components/metier'
import { Bouton, Champ, Chargement, Liste, Message, Panneau, Texte } from '../components/ui'
import { LANGUES, langueCourante, t, type Langue } from '../i18n'
import { CODES_CLASSES, dateHeure, liste, NIVEAUX, nombre, nomClasse, nomLoc, nomSexe, pourcent, triage } from '../lib/format'

function Validation({ a, onMaj }: { a: Analyse; onMaj: (a: Analyse) => void }) {
  const [mode, setMode] = useState<'confirmee' | 'corrigee' | null>(null)
  const [diag, setDiag] = useState('')
  const [commentaire, setCommentaire] = useState('')
  const [histologie, setHistologie] = useState(false)
  const [erreur, setErreur] = useState<string | null>(null)
  const [envoi, setEnvoi] = useState(false)

  if (a.revue !== 'en_attente') {
    return (
      <div className="text-[14.5px]">
        <p><b>{a.revue === 'confirmee' ? t('val.confirmee') : t('val.corrigee')}</b> {t('val.par', { qui: a.relecteur ?? '—', date: dateHeure(a.revue_le) })}</p>
        <p className="mt-1">{t('val.diagRetenu')} <b>{nomClasse(a.diagnostic_final)}</b></p>
        {a.histologie && <p className="mt-1 text-bloc-fonce">{t('val.histologie')}</p>}
        {a.commentaire && <p className="mt-2 text-encre-2">« {a.commentaire} »</p>}
      </div>
    )
  }

  async function envoyer(e: FormEvent) {
    e.preventDefault()
    if (!mode) return
    setEnvoi(true); setErreur(null)
    try {
      onMaj(await api.revue(a.id, { revue: mode, diagnostic_final: mode === 'corrigee' ? diag : null, commentaire: commentaire || null, histologie }))
    } catch (err) {
      setErreur((err as Error).message)
    } finally { setEnvoi(false) }
  }

  return (
    <form onSubmit={envoyer} className="flex flex-col gap-4">
      <p className="text-[14.5px] text-encre-2">{t('val.intro', { classe: nomClasse(a.decision) })}</p>
      <div role="radiogroup" aria-label={t('val.groupe')} className="flex flex-wrap gap-2">
        {([['confirmee', t('val.jeConfirme')], ['corrigee', t('val.jeCorrige')]] as const).map(([v, l]) => (
          <button key={v} type="button" role="radio" aria-checked={mode === v} onClick={() => setMode(v)}
            className={`rounded-[5px] border px-3.5 py-2 text-[14px] font-semibold ${mode === v ? 'border-bloc bg-bloc-pale text-bloc-fonce' : 'border-trait bg-surface hover:border-encre-3'}`}>
            {l}
          </button>
        ))}
      </div>
      {mode === 'corrigee' && (
        <Champ label={t('val.diagnostic')}>{(id) => (
          <Liste id={id} value={diag} onChange={(e) => setDiag(e.target.value)} required>
            <option value="" disabled>{t('val.choisir')}</option>
            {CODES_CLASSES.map((k) => <option key={k} value={k}>{nomClasse(k)}</option>)}
          </Liste>)}
        </Champ>
      )}
      {mode && (
        <>
          <label className="flex items-start gap-2.5 text-[14px]">
            <input type="checkbox" checked={histologie} onChange={(e) => setHistologie(e.target.checked)} className="mt-1 size-4 accent-bloc" />
            <span><span className="font-semibold">{t('val.histoCase')}</span><span className="block text-[13px] text-encre-2">{t('val.histoAide')}</span></span>
          </label>
          <Champ label={t('val.commentaire')} aide={t('val.commentaireAide')}>
            {(id) => <Texte id={id} rows={3} value={commentaire} onChange={(e) => setCommentaire(e.target.value)} maxLength={2000} />}
          </Champ>
        </>
      )}
      {erreur && <Message>{erreur}</Message>}
      {mode && <Bouton type="submit" chargement={envoi} className="self-start">{t('val.enregistrer')}</Bouton>}
    </form>
  )
}

function PanneauEtSi({ a }: { a: Analyse }) {
  const [variable, setVariable] = useState<'age' | 'localisation'>('age')
  const [d, setD] = useState<Record<string, EtSiReponse>>({})
  const [erreur, setErreur] = useState<string | null>(null)
  useEffect(() => {
    if (d[variable]) return
    api.etSi(a.id, variable).then((r) => setD((x) => ({ ...x, [variable]: r }))).catch((e) => setErreur(e.message))
  }, [a.id, variable, d])
  return (
    <Panneau titre={t('etsi.titre')} actions={
      <div role="group" aria-label={t('etsi.variable')} className="inline-flex rounded-[5px] border border-trait p-0.5 text-[13px]">
        {(['age', 'localisation'] as const).map((v) => (
          <button key={v} onClick={() => setVariable(v)} aria-pressed={variable === v}
            className={`rounded-[4px] px-2.5 py-1 font-semibold ${variable === v ? 'bg-bloc text-white' : 'text-encre-2'}`}>
            {v === 'age' ? t('etsi.age') : t('etsi.localisation')}
          </button>
        ))}
      </div>}>
      <p className="mb-3 text-[13.5px] text-encre-2">{t('etsi.intro')}</p>
      {erreur ? <Message>{erreur}</Message> : d[variable] ? <EtSi donnees={d[variable]} /> : <Chargement texte={t('etsi.calcul')} />}
    </Panneau>
  )
}

/** Lien vers le compte rendu PDF, avec choix de la langue (celle de l'interface par défaut). */
function BoutonPDF({ id }: { id: number }) {
  const [langue, setLangue] = useState<Langue>(langueCourante())
  if (DEMO && !pdfDisponible(id)) return null        // en ligne : comptes rendus des cas présentés seulement
  return (
    <div className="inline-flex items-stretch">
      <a href={api.compteRenduUrl(id, langue)} target="_blank" rel="noreferrer">
        <Bouton variante="secondaire" icone={<FileDown className="size-4" aria-hidden />} className="h-full rounded-e-none">{t('ad.pdf')}</Bouton>
      </a>
      <select aria-label={t('ad.pdfLangue')} value={langue} onChange={(e) => setLangue(e.target.value as Langue)}
        className="rounded-e-[5px] border border-s-0 border-trait bg-surface px-2 text-[13.5px] font-semibold text-encre hover:border-encre-3">
        {LANGUES.map((l) => <option key={l.code} value={l.code}>{l.code.toUpperCase()}</option>)}
      </select>
    </div>
  )
}

export function AnalyseDetail() {
  const { id } = useParams()
  const [params] = useSearchParams()
  const [a, setA] = useState<Analyse | null>(null)
  const [erreur, setErreur] = useState<string | null>(null)

  useEffect(() => { api.analyse(Number(id)).then(setA).catch((e) => setErreur(e.message)) }, [id])

  if (erreur) return <Message>{erreur}</Message>
  if (!a) return <Chargement />
  const n = NIVEAUX[a.niveau]
  const { titre, message } = triage(a)
  const couv = pourcent(0.9, 0)
  const calibration = a.calibration?.startsWith('locale:')
    ? t('det.seuilsLocaux', { id: a.calibration.split(':')[1] }) : t('det.seuilsOrigine')

  return (
    <>
      <header className="mb-7 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[14px] text-encre-2">
            <Link to={`/patients/${a.patient_id}`} className="font-semibold text-bloc hover:underline">{a.patient_code}</Link>
            {a.lesion_id && <>{t('commun.liste')}<Link to={`/lesions/${a.lesion_id}`} className="font-semibold text-bloc hover:underline">
              {t('na.lesionN', { n: a.lesion_numero ?? '' })}{a.lesion_nom ? ` — ${a.lesion_nom}` : ''}</Link></>}
            {t('commun.liste')}{nomLoc(a.localisation)}{t('commun.liste')}
            {a.age !== null ? t('commun.ans', { n: a.age }) : t('commun.ageNonPrecise')}{t('commun.liste')}{nomSexe(a.sexe).toLowerCase()}
          </p>
          <h1 className="mt-1 text-[26px] font-bold leading-tight">{t('ad.titre', { date: dateHeure(a.cree_le) })}</h1>
        </div>
        <div className="flex flex-wrap gap-2">
          <BoutonPDF id={a.id} />
          {a.lesion_id && (
            <Link to={`/analyses/nouvelle?patient=${a.patient_id}&lesion=${a.lesion_id}`}>
              <Bouton variante="secondaire" icone={<History className="size-4" aria-hidden />}>{t('ad.nouvelleImage')}</Bouton>
            </Link>
          )}
          <Link to={`/analyses/nouvelle?patient=${a.patient_id}`}>
            <Bouton variante="secondaire" icone={<ScanSearch className="size-4" aria-hidden />}>{t('ad.autreLesion')}</Bouton>
          </Link>
        </div>
      </header>

      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-8 lg:grid-cols-[minmax(0,400px)_minmax(0,1fr)]">
        <Oculaire image={api.imageUrl(a.id, 'image')} carte={api.imageUrl(a.id, 'gradcam')}
          abcd={a.abcd?.A ? api.imageUrl(a.id, 'abcd') : undefined} taille={400} animer={params.has('nouvelle')}
          legendeCarte={t('ad.legendeCarte', { classe: nomClasse(a.decision) })} legendeAbcd={t('ad.legendeAbcd')} />

        <div className="flex min-w-0 flex-col gap-6">
          <section className={`rounded-lg border-s-4 ${n.trait} ${n.fond} px-5 py-4`} aria-live="polite">
            <Statut niveau={a.niveau} />
            <h2 className={`mt-2 text-[22px] font-bold leading-snug ${n.texte}`}>{titre}</h2>
            <p className="mt-1 max-w-prose text-[15px]">{message}</p>
            <div className="mt-3 text-[14px] text-encre-2">
              {a.traite
                ? t('ad.traite', { couv })
                : <>{t('ad.nonTraite', { couv })} <b className="text-encre">{liste(a.ensemble_conforme.map(nomClasse)) || t('commun.aucun')}</b>.</>}
            </div>
            <Avertissements liste={a.avertissements} />
          </section>

          <Panneau titre={t('ad.probas')}>
            <Probabilites probabilites={a.probabilites} decision={a.decision} ensemble={a.ensemble_conforme} seuilMel={a.seuil_melanome} />
          </Panneau>
        </div>
      </div>

      <div className="mt-8 grid grid-cols-[minmax(0,1fr)] items-start gap-6 lg:grid-cols-2">
        {a.abcd && <Panneau titre={t('abcd.titre')}><CriteresABCD m={a.abcd} /></Panneau>}
        {a.evolution && a.lesion_id && (
          <Panneau titre={t('evo.titre')}><PanneauEvolution evo={a.evolution} lesionId={a.lesion_id} analyseId={a.id} /></Panneau>
        )}
        <PanneauEtSi a={a} />
        <Panneau titre={t('val.titre')}><Validation a={a} onMaj={setA} /></Panneau>
      </div>

      <details className="mt-8 text-[13.5px] text-encre-2">
        <summary className="cursor-pointer font-semibold text-encre">{t('det.titre')}</summary>
        <dl className="mt-3 grid max-w-2xl grid-cols-[auto_1fr] gap-x-6 gap-y-1">
          <dt>{t('det.modele')}</dt><dd dir="ltr" className="text-start">{a.modele} v{a.version_modele}</dd>
          <dt>{t('det.profil')}</dt><dd>{a.profil === 'complet' ? t('det.profilComplet') : t('det.profilSans')}</dd>
          <dt>{t('det.regle')}</dt><dd>{t('det.regleTexte', { R: a.rapport_cout, seuil: nombre(a.seuil_melanome) })}</dd>
          <dt>{t('det.seuils')}</dt><dd>{calibration}</dd>
          {a.score_hors_sujet !== null && <>
            <dt>{t('det.atypie')}</dt>
            <dd>{nombre(a.score_hors_sujet, 1)}{a.hors_sujet_force && <span className="text-avis">{t('commun.liste')}{t('det.force')}</span>}</dd>
          </>}
          <dt>{t('det.duree')}</dt><dd>{t('commun.ms', { n: a.duree_ms })}</dd>
          <dt>{t('det.demandePar')}</dt><dd>{a.auteur}</dd>
          <dt>{t('det.identifiant')}</dt><dd className="break-all">{a.uid}</dd>
        </dl>
      </details>
    </>
  )
}
