import { ImageOff, ImagePlus, Plus, Search, UserPlus, X } from 'lucide-react'
import { useEffect, useRef, useState, type DragEvent, type FormEvent, type ReactNode } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, ErreurApi, type Lesion, type Patient, type Sexe } from '../api'
import { CarteCorps } from '../components/CarteCorps'
import { Oculaire, Statut } from '../components/metier'
import { Bouton, Champ, Dialogue, EnTete, Liste, Message, Saisie } from '../components/ui'
import { useApp } from '../contexte'
import { DEMO } from '../demoStatique'
import { t } from '../i18n'
import { ageDepuis, ANNEE_COURANTE, CODES_LOCALISATIONS, CODES_SEXES, date, entier, nombre, nomLoc, nomSexe } from '../lib/format'

const TYPES = ['image/jpeg', 'image/png', 'image/tiff', 'image/bmp', 'image/webp']

function Etape({ n, titre, fait, children }: { n: number; titre: string; fait: boolean; children: ReactNode }) {
  return (
    <section className="grid grid-cols-[32px_1fr] gap-x-4 border-t border-trait py-6 first:border-t-0 first:pt-0">
      <span aria-hidden className={`grid size-8 place-items-center rounded-full text-[14px] font-bold
        ${fait ? 'bg-bloc text-white' : 'border border-trait bg-surface text-encre-2'}`}>{n}</span>
      <div className="min-w-0">
        <h2 className="mb-3 pt-1 text-[17px] font-bold">{titre}</h2>
        {children}
      </div>
    </section>
  )
}

function ChoixPatient({ patient, onChoix }: { patient: Patient | null; onChoix: (p: Patient | null) => void }) {
  const [q, setQ] = useState('')
  const [resultats, setResultats] = useState<Patient[]>([])
  const [creation, setCreation] = useState(false)
  const [f, setF] = useState({ annee: '', sexe: 'unknown' as Sexe, ref: '' })
  const [erreur, setErreur] = useState<string | null>(null)

  useEffect(() => {
    if (patient || creation) return
    const minuteur = setTimeout(() => api.patients(q).then((r) => setResultats(r.elements.slice(0, 6))).catch(() => undefined), 200)
    return () => clearTimeout(minuteur)
  }, [q, patient, creation])

  async function creer() {
    setErreur(null)
    try {
      onChoix(await api.creerPatient({ annee_naissance: f.annee ? Number(f.annee) : null, sexe: f.sexe, reference_externe: f.ref || null, notes: null }))
      setCreation(false)
    } catch (e) { setErreur((e as Error).message) }
  }

  if (patient) {
    const details = [nomSexe(patient.sexe), patient.annee_naissance ? t('na.neEn', { annee: patient.annee_naissance }) : '',
      patient.reference_externe ? t('na.dossier', { ref: patient.reference_externe }) : '', t('na.nbAnalyses', { n: patient.nb_analyses })]
    return (
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-[5px] border border-trait bg-surface px-4 py-3">
        <div>
          <p className="font-bold">{patient.code}</p>
          <p className="text-[13.5px] text-encre-2">{details.filter(Boolean).join(t('commun.liste'))}</p>
        </div>
        <Bouton variante="discret" onClick={() => onChoix(null)} icone={<X className="size-4" aria-hidden />}>{t('na.changerPatient')}</Bouton>
      </div>
    )
  }
  if (creation) {
    return (
      <div className="flex flex-col gap-3 rounded-[5px] border border-trait bg-surface p-4">
        {erreur && <Message>{erreur}</Message>}
        <div className="grid gap-3 sm:grid-cols-3">
          <Champ label={t('na.anneeNaissance')}>{(id) => <Saisie id={id} type="number" min={1900} max={ANNEE_COURANTE} value={f.annee} onChange={(e) => setF({ ...f, annee: e.target.value })} />}</Champ>
          <Champ label={t('na.sexe')}>{(id) => (
            <Liste id={id} value={f.sexe} onChange={(e) => setF({ ...f, sexe: e.target.value as Sexe })}>
              {CODES_SEXES.map((s) => <option key={s} value={s}>{nomSexe(s)}</option>)}
            </Liste>)}
          </Champ>
          <Champ label={t('na.numDossier')}>{(id) => <Saisie id={id} value={f.ref} onChange={(e) => setF({ ...f, ref: e.target.value })} />}</Champ>
        </div>
        <p className="text-[13px] text-encre-2">{t('na.pseudonyme')}</p>
        <div className="flex gap-2">
          <Bouton type="button" onClick={creer}>{t('na.creerPatient')}</Bouton>
          <Bouton type="button" variante="secondaire" onClick={() => setCreation(false)}>{t('commun.annuler')}</Bouton>
        </div>
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-2">
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-encre-3" aria-hidden />
          <Saisie aria-label={t('na.rechercher')} placeholder={t('na.placeholderRecherche')} value={q} onChange={(e) => setQ(e.target.value)} className="ps-9" />
        </div>
        <Bouton type="button" variante="secondaire" onClick={() => setCreation(true)} icone={<UserPlus className="size-4" aria-hidden />}>{t('na.nouveauPatient')}</Bouton>
      </div>
      {resultats.length > 0 && (
        <ul className="divide-y divide-trait-2 rounded-[5px] border border-trait bg-surface">
          {resultats.map((p) => (
            <li key={p.id}>
              <button type="button" onClick={() => onChoix(p)} className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-start hover:bg-porcelaine">
                <span className="font-semibold">{p.code}</span>
                <span className="text-[13.5px] text-encre-2">
                  {[nomSexe(p.sexe), p.annee_naissance ? t('commun.ans', { n: ageDepuis(p.annee_naissance) ?? '' }) : '', p.reference_externe ?? '']
                    .filter(Boolean).join(t('commun.liste'))}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** Nouvelle lésion, ou nouvelle image d'une lésion déjà suivie (comparaison automatique avec la précédente). */
function ChoixLesion({ lesions, choisie, onChoix }: { lesions: Lesion[]; choisie: number | null; onChoix: (l: Lesion | null) => void }) {
  const carte = (actif: boolean) => `flex w-full items-center gap-3 rounded-[5px] border px-3 py-2.5 text-start
    ${actif ? 'border-bloc bg-bloc-pale' : 'border-trait bg-surface hover:border-encre-3'}`
  return (
    <div className="flex flex-col gap-2">
      <p className="mb-1 max-w-prose text-[13.5px] text-encre-2">{t('na.lesionIntro')}</p>
      <div role="radiogroup" aria-label={t('na.etapeLesion')} className="grid gap-2 sm:grid-cols-2">
        <button type="button" role="radio" aria-checked={choisie === null} onClick={() => onChoix(null)} className={carte(choisie === null)}>
          <span className="grid size-11 shrink-0 place-items-center rounded-full border border-dashed border-encre-3/60 text-encre-2"><Plus className="size-5" aria-hidden /></span>
          <span className="font-semibold">{t('na.nouvelleLesion')}</span>
        </button>
        {lesions.map((l) => (
          <button key={l.id} type="button" role="radio" aria-checked={choisie === l.id} onClick={() => onChoix(l)} className={carte(choisie === l.id)}>
            {l.derniere_image
              ? <img src={api.imageUrl(l.derniere_image, 'image')} alt="" className="size-11 shrink-0 rounded-full object-cover ring-2 ring-derme" />
              : <span className="size-11 shrink-0 rounded-full bg-trait-2" />}
            <span className="min-w-0">
              <span className="block truncate font-semibold">{t('na.lesionN', { n: l.numero })}{l.nom ? ` — ${l.nom}` : ''}</span>
              <span className="block truncate text-[13px] text-encre-2">
                {nomLoc(l.localisation)}{l.derniere_analyse ? `${t('commun.liste')}${t('na.derniereImage', { date: date(l.derniere_analyse) })}` : ''}
              </span>
              {l.dernier_niveau && <span className="mt-1 block"><Statut niveau={l.dernier_niveau} taille="petite" /></span>}
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}

export function NouvelleAnalyse() {
  const { etat } = useApp()
  const naviguer = useNavigate()
  const [params] = useSearchParams()
  const [patient, setPatient] = useState<Patient | null>(null)
  const [lesions, setLesions] = useState<Lesion[]>([])
  const [lesion, setLesion] = useState<Lesion | null>(null)
  const [fichier, setFichier] = useState<File | null>(null)
  const [apercu, setApercu] = useState<string | null>(null)
  const [loc, setLoc] = useState('')
  const [age, setAge] = useState('')
  const [sexe, setSexe] = useState<Sexe>('unknown')
  const [erreur, setErreur] = useState<string | null>(null)
  const [envoi, setEnvoi] = useState(false)
  const [survol, setSurvol] = useState(false)
  const [horsSujet, setHorsSujet] = useState<{ score: number; seuil: number } | null>(null)
  const entree = useRef<HTMLInputElement>(null)

  // Choisir un patient pré-remplit l'âge (depuis l'année de naissance) et le sexe, modifiables ensuite.
  function choisirPatient(p: Patient | null, lesionVoulue?: number) {
    setPatient(p)
    setAge(p?.annee_naissance ? String(ageDepuis(p.annee_naissance)) : '')
    setSexe(p?.sexe ?? 'unknown')
    setLesion(null)
    setLesions([])
    if (p) {
      api.lesionsDuPatient(p.id).then((ls) => {
        setLesions(ls)
        const l = ls.find((x) => x.id === lesionVoulue)
        if (l) choisirLesion(l)
      }).catch(() => undefined)
    }
  }

  function choisirLesion(l: Lesion | null) {
    setLesion(l)
    if (l && l.localisation !== 'unknown') setLoc(l.localisation)
  }

  useEffect(() => {
    const id = Number(params.get('patient'))
    const idLesion = Number(params.get('lesion')) || undefined
    if (id) api.patient(id).then((p) => choisirPatient(p, idLesion)).catch(() => undefined)
  }, [params])

  useEffect(() => () => { if (apercu) URL.revokeObjectURL(apercu) }, [apercu])

  function choisirFichier(f: File | undefined) {
    setErreur(null)
    if (!f) return
    if (!TYPES.includes(f.type)) { setErreur(t('na.formatInvalide')); return }
    if (f.size > 15 * 1024 * 1024) { setErreur(t('na.tropVolumineuse')); return }
    setFichier(f)
    setApercu(URL.createObjectURL(f))
  }

  const deposer = (e: DragEvent) => { e.preventDefault(); setSurvol(false); choisirFichier(e.dataTransfer.files[0]) }
  const contexteComplet = age !== '' && sexe !== 'unknown' && loc !== '' && loc !== 'unknown'
  const pret = patient && fichier && loc && etat?.modele.charge

  async function envoyer(forcer: boolean) {
    if (!pret || !patient || !fichier) return
    setEnvoi(true); setErreur(null); setHorsSujet(null)
    const fd = new FormData()
    fd.set('patient_id', String(patient.id))
    fd.set('localisation', loc)
    fd.set('sexe', sexe)
    if (age !== '') fd.set('age', age)
    if (lesion) fd.set('lesion_id', String(lesion.id))
    if (forcer) fd.set('forcer', 'true')
    fd.set('image', fichier)
    try {
      const a = await api.creerAnalyse(fd)
      naviguer(`/analyses/${a.id}?nouvelle=1`)
    } catch (err) {
      if (err instanceof ErreurApi && err.code === 'image_hors_sujet') {
        setHorsSujet({ score: Number(err.details?.score), seuil: Number(err.details?.seuil) })
      } else {
        setErreur((err as Error).message)
      }
      setEnvoi(false)
    }
  }

  const analyser = (e: FormEvent) => { e.preventDefault(); void envoyer(false) }

  return (
    <>
      <EnTete titre={t('nav.nouvelleAnalyse')} sousTitre={t('na.sousTitre')} />
      {DEMO && <div className="mb-6"><Message type="info">{t('demo.nouvelleAnalyse')}</Message></div>}
      <form onSubmit={analyser} className="grid grid-cols-[minmax(0,1fr)] gap-10 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div>
          <Etape n={1} titre={t('na.etapePatient')} fait={!!patient}><ChoixPatient patient={patient} onChoix={(p) => choisirPatient(p)} /></Etape>
          <Etape n={2} titre={t('na.etapeLesion')} fait={!!patient}>
            {patient ? <ChoixLesion lesions={lesions} choisie={lesion?.id ?? null} onChoix={choisirLesion} />
              : <p className="text-[14px] text-encre-2">{t('na.choisirPatientDabord')}</p>}
          </Etape>
          <Etape n={3} titre={t('na.etapeImage')} fait={!!fichier}>
            <div onDragOver={(e) => { e.preventDefault(); setSurvol(true) }} onDragLeave={() => setSurvol(false)} onDrop={deposer}
              className={`flex flex-col items-start gap-3 rounded-[5px] border border-dashed px-5 py-5 ${survol ? 'border-bloc bg-bloc-pale' : 'border-encre-3/50 bg-surface'}`}>
              <p className="text-[14.5px]">{fichier ? <><b>{fichier.name}</b> ({t('commun.mo', { n: nombre(fichier.size / 1e6, 1) })})</> : t('na.deposer')}</p>
              <input ref={entree} type="file" accept={TYPES.join(',')} className="hidden" onChange={(e) => { choisirFichier(e.target.files?.[0]); e.target.value = '' }} />
              <Bouton type="button" variante="secondaire" onClick={() => entree.current?.click()} icone={<ImagePlus className="size-4" aria-hidden />}>
                {fichier ? t('na.remplacer') : t('na.choisirImage')}
              </Bouton>
              <p className="text-[13px] text-encre-2">{t('na.aideImage')}</p>
            </div>
          </Etape>
          <Etape n={4} titre={t('na.etapeLoc')} fait={!!loc}>
            {lesion && loc === lesion.localisation && <p className="mb-3 text-[13.5px] text-encre-2">{t('na.locLesion')}</p>}
            <CarteCorps valeur={loc} onChange={setLoc} />
            <div className="mx-auto mt-4 max-w-sm">
              <Champ label={t('na.ouListe')}>{(id) => (
                <Liste id={id} value={loc} onChange={(e) => setLoc(e.target.value)}>
                  <option value="" disabled>{t('na.choisirLoc')}</option>
                  {CODES_LOCALISATIONS.map((k) => <option key={k} value={k}>{nomLoc(k)}</option>)}
                </Liste>)}
              </Champ>
            </div>
          </Etape>
          <Etape n={5} titre={t('na.etapeContexte')} fait={contexteComplet}>
            <div className="grid max-w-md gap-3 sm:grid-cols-2">
              <Champ label={t('na.age')} aide={patient?.annee_naissance ? t('na.ageCalcule') : undefined}>
                {(id) => <Saisie id={id} type="number" min={0} max={120} value={age} onChange={(e) => setAge(e.target.value)} />}
              </Champ>
              <Champ label={t('na.sexe')}>{(id) => (
                <Liste id={id} value={sexe} onChange={(e) => setSexe(e.target.value as Sexe)}>
                  {CODES_SEXES.map((s) => <option key={s} value={s}>{nomSexe(s)}</option>)}
                </Liste>)}
              </Champ>
            </div>
            <p className="mt-3 max-w-prose text-[13.5px] text-encre-2">
              {contexteComplet ? t('na.contexteComplet') : t('na.contexteIncomplet')}
            </p>
          </Etape>
        </div>
        <aside className="lg:sticky lg:top-8 lg:self-start">
          <div className="rounded-lg border border-trait bg-surface px-5 py-6">
            {apercu ? <Oculaire image={apercu} taille={300} /> : (
              <div className="mx-auto grid aspect-square w-[260px] place-items-center rounded-full border border-dashed border-encre-3/50 text-center text-[14px] text-encre-2">
                {t('na.apercu')}
              </div>
            )}
            <dl className="mt-5 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[14px]">
              <dt className="text-encre-2">{t('na.patient')}</dt><dd className="font-semibold">{patient?.code ?? '—'}</dd>
              <dt className="text-encre-2">{t('na.lesion')}</dt>
              <dd className="font-semibold">{patient ? (lesion ? t('na.lesionN', { n: lesion.numero }) : t('na.nouvelleLesion')) : '—'}</dd>
              <dt className="text-encre-2">{t('na.localisation')}</dt><dd className="font-semibold">{loc ? nomLoc(loc) : '—'}</dd>
              <dt className="text-encre-2">{t('na.ageSexe')}</dt>
              <dd className="font-semibold">{age ? t('commun.ans', { n: entier(Number(age)) }) : t('commun.ageNonPrecise')}{t('commun.liste')}{nomSexe(sexe).toLowerCase()}</dd>
            </dl>
            {erreur && <div className="mt-4"><Message>{erreur}</Message></div>}
            <Bouton type="submit" disabled={!pret} chargement={envoi} className="mt-5 w-full py-2.5">
              {envoi ? t('na.enCours') : t('na.analyser')}
            </Bouton>
            {!pret && !envoi && <p className="mt-2 text-center text-[13px] text-encre-2">{t('na.completer')}</p>}
          </div>
        </aside>
      </form>

      <Dialogue ouvert={horsSujet !== null} titre={t('hs.titre')} onFermer={() => setHorsSujet(null)}>
        <div className="flex gap-3">
          <ImageOff className="mt-0.5 size-6 shrink-0 text-avis" aria-hidden />
          <div className="text-[14.5px]">
            <p>{t('hs.texte')}</p>
            {horsSujet && <p className="mt-2 text-[13px] text-encre-2">{t('hs.score', { score: nombre(horsSujet.score, 1), seuil: nombre(horsSujet.seuil, 1) })}</p>}
          </div>
        </div>
        <div className="mt-5 flex flex-wrap gap-2">
          <Bouton onClick={() => { setHorsSujet(null); setFichier(null); setApercu(null); entree.current?.click() }}
            icone={<ImagePlus className="size-4" aria-hidden />}>{t('hs.autre')}</Bouton>
          <Bouton variante="secondaire" onClick={() => void envoyer(true)}>{t('hs.forcer')}</Bouton>
        </div>
        <p className="mt-3 text-[12.5px] text-encre-2">{t('hs.forcerAide')}</p>
      </Dialogue>
    </>
  )
}
