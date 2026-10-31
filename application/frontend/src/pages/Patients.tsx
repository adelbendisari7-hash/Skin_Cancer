import { History, ScanSearch, Search, UserPlus } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, type Analyse, type Lesion, type Page, type Patient, type Sexe } from '../api'
import { Statut } from '../components/metier'
import { Bouton, Champ, Chargement, Dialogue, EnTete, Liste, Message, Panneau, Saisie, Texte, Vide } from '../components/ui'
import { t } from '../i18n'
import { ageDepuis, ANNEE_COURANTE, CODES_SEXES, date, dateHeure, nomClasse, nomLoc, nomSexe } from '../lib/format'

function FormulairePatient({ initial, onFini }: { initial?: Patient; onFini: (p: Patient) => void }) {
  const [f, setF] = useState({
    annee: initial?.annee_naissance ? String(initial.annee_naissance) : '', sexe: initial?.sexe ?? ('unknown' as Sexe),
    ref: initial?.reference_externe ?? '', notes: initial?.notes ?? '',
  })
  const [erreur, setErreur] = useState<string | null>(null)
  const [envoi, setEnvoi] = useState(false)
  async function envoyer(e: FormEvent) {
    e.preventDefault()
    setEnvoi(true); setErreur(null)
    const d = { annee_naissance: f.annee ? Number(f.annee) : null, sexe: f.sexe, reference_externe: f.ref || null, notes: f.notes || null }
    try { onFini(initial ? await api.modifierPatient(initial.id, d) : await api.creerPatient(d)) }
    catch (err) { setErreur((err as Error).message) } finally { setEnvoi(false) }
  }
  return (
    <form onSubmit={envoyer} className="flex flex-col gap-4">
      {erreur && <Message>{erreur}</Message>}
      <div className="grid gap-4 sm:grid-cols-2">
        <Champ label={t('na.anneeNaissance')}>{(id) => <Saisie id={id} type="number" min={1900} max={ANNEE_COURANTE} value={f.annee} onChange={(e) => setF({ ...f, annee: e.target.value })} />}</Champ>
        <Champ label={t('pat.sexe')}>{(id) => (
          <Liste id={id} value={f.sexe} onChange={(e) => setF({ ...f, sexe: e.target.value as Sexe })}>
            {CODES_SEXES.map((s) => <option key={s} value={s}>{nomSexe(s)}</option>)}
          </Liste>)}
        </Champ>
      </div>
      <Champ label={t('pat.dossierLogiciel')} aide={t('pat.dossierAide')}>
        {(id) => <Saisie id={id} value={f.ref} onChange={(e) => setF({ ...f, ref: e.target.value })} maxLength={64} />}
      </Champ>
      <Champ label={t('pat.notes')}>{(id) => <Texte id={id} rows={3} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} maxLength={2000} />}</Champ>
      <Bouton type="submit" chargement={envoi} className="self-start">{initial ? t('pat.enregistrer') : t('na.creerPatient')}</Bouton>
    </form>
  )
}

export function Patients() {
  const naviguer = useNavigate()
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const [donnees, setDonnees] = useState<Page<Patient> | null>(null)
  const [creation, setCreation] = useState(false)
  const [erreur, setErreur] = useState<string | null>(null)

  useEffect(() => {
    const minuteur = setTimeout(() => api.patients(q, page).then(setDonnees).catch((e) => setErreur(e.message)), 180)
    return () => clearTimeout(minuteur)
  }, [q, page])

  return (
    <>
      <EnTete titre={t('nav.patients')} sousTitre={t('pat.sousTitre')}
        actions={<Bouton onClick={() => setCreation(true)} icone={<UserPlus className="size-4" aria-hidden />}>{t('na.nouveauPatient')}</Bouton>} />
      <div className="relative mb-4 max-w-md">
        <Search className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-encre-3" aria-hidden />
        <Saisie aria-label={t('pat.rechercher')} placeholder={t('na.placeholderRecherche')} value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} className="ps-9" />
      </div>
      {erreur && <Message>{erreur}</Message>}
      {!donnees ? <Chargement /> : donnees.total === 0 ? (
        <Vide titre={q ? t('pat.aucunCorrespond') : t('pat.aucun')} texte={q ? t('pat.verifier') : t('pat.creezTexte')} />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-trait bg-surface">
          <table className="w-full text-start text-[14px]">
            <thead className="border-b border-trait text-[13px] text-encre-2">
              <tr><th className="px-4 py-2.5 text-start font-semibold">{t('pat.code')}</th><th className="px-4 text-start font-semibold">{t('pat.dossier')}</th>
                <th className="px-4 text-start font-semibold">{t('pat.age')}</th><th className="px-4 text-start font-semibold">{t('pat.sexe')}</th>
                <th className="px-4 text-start font-semibold">{t('pat.analyses')}</th><th className="px-4 text-start font-semibold">{t('pat.derniere')}</th></tr>
            </thead>
            <tbody className="divide-y divide-trait-2">
              {donnees.elements.map((p) => (
                <tr key={p.id} onClick={() => naviguer(`/patients/${p.id}`)} className="cursor-pointer hover:bg-porcelaine">
                  <td className="px-4 py-3"><Link to={`/patients/${p.id}`} className="font-semibold text-bloc hover:underline">{p.code}</Link></td>
                  <td className="px-4 text-encre-2">{p.reference_externe ?? '—'}</td>
                  <td className="chiffres px-4">{p.annee_naissance ? t('commun.ans', { n: ageDepuis(p.annee_naissance) ?? '' }) : '—'}</td>
                  <td className="px-4">{nomSexe(p.sexe)}</td>
                  <td className="chiffres px-4">{p.nb_analyses}</td>
                  <td className="px-4 text-encre-2">{date(p.derniere_analyse)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {donnees && donnees.total > 25 && (
        <div className="mt-4 flex items-center gap-3 text-[14px]">
          <Bouton variante="secondaire" disabled={page === 1} onClick={() => setPage(page - 1)}>{t('commun.precedent')}</Bouton>
          <span>{t('commun.pageSur', { page, total: Math.ceil(donnees.total / 25) })}</span>
          <Bouton variante="secondaire" disabled={page * 25 >= donnees.total} onClick={() => setPage(page + 1)}>{t('commun.suivant')}</Bouton>
        </div>
      )}
      <Dialogue ouvert={creation} titre={t('na.nouveauPatient')} onFermer={() => setCreation(false)}>
        <FormulairePatient onFini={(p) => naviguer(`/patients/${p.id}`)} />
      </Dialogue>
    </>
  )
}

function CarteLesion({ l }: { l: Lesion }) {
  return (
    <Link to={`/lesions/${l.id}`} className="flex gap-3 rounded-[5px] border border-trait p-3 hover:border-encre-3">
      {l.derniere_image
        ? <img src={api.imageUrl(l.derniere_image, 'image')} alt="" className="size-16 shrink-0 rounded-full object-cover ring-2 ring-derme" />
        : <span className="size-16 shrink-0 rounded-full bg-trait-2" />}
      <div className="min-w-0">
        <p className="truncate text-[14.5px] font-semibold">{t('na.lesionN', { n: l.numero })}{l.nom ? ` — ${l.nom}` : ''}</p>
        <p className="truncate text-[13px] text-encre-2">{nomLoc(l.localisation)}{t('commun.liste')}{t('pat.nbImages', { n: l.nb_analyses })}</p>
        <p className="truncate text-[13px] text-encre-2">{date(l.derniere_analyse)}</p>
        <div className="mt-1 flex flex-wrap gap-1.5">
          {l.dernier_niveau && <Statut niveau={l.dernier_niveau} taille="petite" />}
          {l.evolution_notable && (
            <span className="inline-flex items-center gap-1 rounded-[4px] bg-avis-pale px-1.5 py-0.5 text-[12px] font-semibold text-avis">
              <History className="size-3.5" aria-hidden /> {t('pat.evolutionNotable')}
            </span>
          )}
        </div>
      </div>
    </Link>
  )
}

export function PatientDetail() {
  const { id } = useParams()
  const [p, setP] = useState<Patient | null>(null)
  const [analyses, setAnalyses] = useState<Analyse[] | null>(null)
  const [lesions, setLesions] = useState<Lesion[] | null>(null)
  const [edition, setEdition] = useState(false)
  const [erreur, setErreur] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([api.patient(Number(id)), api.analysesDuPatient(Number(id)), api.lesionsDuPatient(Number(id))])
      .then(([pp, aa, ll]) => { setP(pp); setAnalyses(aa); setLesions(ll) }).catch((e) => setErreur(e.message))
  }, [id])

  if (erreur) return <Message>{erreur}</Message>
  if (!p || !analyses || !lesions) return <Chargement />
  const sousTitre = [nomSexe(p.sexe), p.annee_naissance ? t('pat.ageNe', { age: ageDepuis(p.annee_naissance) ?? '', annee: p.annee_naissance }) : '',
    p.reference_externe ? t('na.dossier', { ref: p.reference_externe }) : ''].filter(Boolean).join(t('commun.liste'))
  return (
    <>
      <EnTete titre={p.code} sousTitre={sousTitre}
        actions={<>
          <Bouton variante="secondaire" onClick={() => setEdition(true)}>{t('pat.modifier')}</Bouton>
          <Link to={`/analyses/nouvelle?patient=${p.id}`}><Bouton icone={<ScanSearch className="size-4" aria-hidden />}>{t('nav.nouvelleAnalyse')}</Bouton></Link>
        </>} />
      {p.notes && <p className="mb-6 max-w-prose text-[14.5px] text-encre-2">{p.notes}</p>}
      <Panneau titre={t('pat.lesions', { n: lesions.length })}>
        {lesions.length === 0 ? (
          <Vide titre={t('pat.aucuneAnalyse')} action={<Link to={`/analyses/nouvelle?patient=${p.id}`} className="font-semibold text-bloc hover:underline">{t('pat.analyserLesion')}</Link>} />
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {lesions.map((l) => <li key={l.id}><CarteLesion l={l} /></li>)}
          </ul>
        )}
      </Panneau>
      {analyses.length > 0 && (
        <Panneau titre={t('pat.toutesAnalyses', { n: analyses.length })} className="mt-6">
          <ul className="-mx-5 divide-y divide-trait-2">
            {analyses.map((a) => (
              <li key={a.id}>
                <Link to={`/analyses/${a.id}`} className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-4 px-5 py-2.5 hover:bg-porcelaine">
                  <img src={api.imageUrl(a.id, 'image')} alt="" className="size-10 rounded-full object-cover ring-2 ring-derme" />
                  <div className="min-w-0">
                    <p className="truncate text-[14px] font-semibold">
                      {a.lesion_numero ? `${t('na.lesionN', { n: a.lesion_numero })}${t('commun.liste')}` : ''}{nomLoc(a.localisation)}
                    </p>
                    <p className="truncate text-[13px] text-encre-2">
                      {dateHeure(a.cree_le)}{t('commun.liste')}
                      {a.revue === 'en_attente' ? t('pat.aValider') : t('pat.retenu', { classe: nomClasse(a.diagnostic_final) })}
                    </p>
                  </div>
                  <Statut niveau={a.niveau} taille="petite" />
                </Link>
              </li>
            ))}
          </ul>
        </Panneau>
      )}
      <Dialogue ouvert={edition} titre={t('pat.modifierCode', { code: p.code })} onFermer={() => setEdition(false)}>
        <FormulairePatient initial={p} onFini={(pp) => { setP(pp); setEdition(false) }} />
      </Dialogue>
    </>
  )
}

export function Analyses() {
  const [params, setParams] = useSearchParams()
  const statut = params.get('statut') ?? ''
  const revue = params.get('revue') ?? ''
  const page = Number(params.get('page') ?? 1)
  const [donnees, setDonnees] = useState<Page<Analyse> | null>(null)
  const [erreur, setErreur] = useState<string | null>(null)
  useEffect(() => { api.analyses({ statut, revue, page }).then(setDonnees).catch((e) => setErreur(e.message)) }, [statut, revue, page])
  const filtre = (k: string, v: string) => { const n = new URLSearchParams(params); if (v) n.set(k, v); else n.delete(k); n.delete('page'); setParams(n) }
  const allerPage = (p: number) => { const n = new URLSearchParams(params); n.set('page', String(p)); setParams(n) }

  return (
    <>
      <EnTete titre={t('nav.analyses')} sousTitre={t('an.sousTitre')} />
      <div className="mb-4 flex flex-wrap gap-3">
        <Liste aria-label={t('an.orientation')} value={statut} onChange={(e) => filtre('statut', e.target.value)} className="w-auto">
          <option value="">{t('an.toutesOrientations')}</option>
          <option value="alerte_melanome">{t('an.urgentMel')}</option>
          <option value="maligne_probable">{t('niveau.eleve')}</option>
          <option value="incertain">{t('niveau.renvoi')}</option>
          <option value="benigne_probable">{t('niveau.faible')}</option>
        </Liste>
        <Liste aria-label={t('an.validation')} value={revue} onChange={(e) => filtre('revue', e.target.value)} className="w-auto">
          <option value="">{t('an.toutesValidations')}</option>
          <option value="en_attente">{t('an.aValider')}</option>
          <option value="confirmee">{t('an.confirmees')}</option>
          <option value="corrigee">{t('an.corrigees')}</option>
        </Liste>
      </div>
      {erreur && <Message>{erreur}</Message>}
      {!donnees ? <Chargement /> : donnees.total === 0 ? <Vide titre={t('an.aucune')} /> : (
        <div className="overflow-x-auto rounded-lg border border-trait bg-surface">
          <table className="w-full text-start text-[14px]">
            <thead className="border-b border-trait text-[13px] text-encre-2">
              <tr><th className="px-4 py-2.5 text-start font-semibold">{t('an.date')}</th><th className="px-4 text-start font-semibold">{t('an.patient')}</th>
                <th className="px-4 text-start font-semibold">{t('an.localisation')}</th><th className="px-4 text-start font-semibold">{t('an.orientation')}</th>
                <th className="px-4 text-start font-semibold">{t('an.proposition')}</th><th className="px-4 text-start font-semibold">{t('an.validation')}</th></tr>
            </thead>
            <tbody className="divide-y divide-trait-2">
              {donnees.elements.map((a) => (
                <tr key={a.id} className="hover:bg-porcelaine">
                  <td className="px-4 py-3 whitespace-nowrap"><Link to={`/analyses/${a.id}`} className="font-semibold text-bloc hover:underline">{dateHeure(a.cree_le)}</Link></td>
                  <td className="px-4">{a.patient_code}</td>
                  <td className="px-4">{nomLoc(a.localisation)}</td>
                  <td className="px-4"><Statut niveau={a.niveau} taille="petite" /></td>
                  <td className="px-4">{nomClasse(a.decision)}</td>
                  <td className="px-4 text-encre-2">{a.revue === 'en_attente' ? t('an.aValider') : a.revue === 'confirmee' ? t('an.confirmee') : t('an.corrigeeDiag', { classe: nomClasse(a.diagnostic_final) })}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {donnees && donnees.total > 25 && (
        <div className="mt-4 flex items-center gap-3 text-[14px]">
          <Bouton variante="secondaire" disabled={page === 1} onClick={() => allerPage(page - 1)}>{t('commun.precedent')}</Bouton>
          <span>{t('commun.pageSur', { page, total: Math.ceil(donnees.total / 25) })}</span>
          <Bouton variante="secondaire" disabled={page * 25 >= donnees.total} onClick={() => allerPage(page + 1)}>{t('commun.suivant')}</Bouton>
        </div>
      )}
    </>
  )
}
