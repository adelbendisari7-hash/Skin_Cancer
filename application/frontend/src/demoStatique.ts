// Démonstration en ligne (construction Vercel, VITE_DEMO_STATIQUE=1) : l'interface lit un instantané des réponses
// réelles de l'API (outils/exporter_demo_statique.py). Les analyses du visiteur tournent dans son navigateur
// (src/navigateur) et restent dans IndexedDB, sur son appareil : aucune image n'est envoyée à un serveur.
// La version installée de l'application n'utilise jamais ce module.
import { t } from './i18n'
import type { Progres } from './navigateur/moteur'

export const DEMO = import.meta.env.VITE_DEMO_STATIQUE === '1'
const SESSION = 'dermia.demo.connecte'
const TAILLE_PAGE = 25
const BASE_LOCALE = 1_000_000                       // identifiants des patients, lésions et analyses du visiteur

type Element = Record<string, unknown> & { id: number }
interface DetailLesion { lesion: unknown; patient_code: string; ids: number[]; defaut: unknown; paires: Record<string, unknown> }
interface Instantane {
  etat: unknown
  moi: unknown
  tableau: unknown
  patients: Element[]
  analyses: Element[]
  lesions: Record<string, unknown[]>
  details: Record<string, DetailLesion>
  etsi: Record<string, unknown>
  fiche: unknown
  parametres: unknown
  utilisateurs: unknown
  journal: Element[]
  recalibrage: unknown
  sauvegardes: unknown
  pdf: number[]
}

/** Refus d'une action en démonstration ; api.ts le convertit en ErreurApi. */
export class RefusDemo extends Error {
  readonly statut: number
  readonly details?: Record<string, unknown>
  constructor(statut: number, message: string, details?: Record<string, unknown>) {
    super(message)
    this.statut = statut
    this.details = details
  }
}

// ---- stockage local du visiteur (IndexedDB) -----------------------------------------------------
const BASE = 'dermia-demo', MAGASIN = 'donnees'
// Condition écrite ici même : la construction locale élimine ainsi tout le moteur du navigateur de l'application installée.
const chargerMoteur = () => (import.meta.env.VITE_DEMO_STATIQUE === '1' ? import('./navigateur/moteur') : Promise.reject(new Error('demo')))
let surProgres: ((p: Progres | null) => void) | null = null
export const suivreProgres = (f: ((p: Progres | null) => void) | null) => { surProgres = f }

function ouvrir(): Promise<IDBDatabase> {
  return new Promise((ok, ko) => {
    const r = indexedDB.open(BASE, 1)
    r.onupgradeneeded = () => r.result.createObjectStore(MAGASIN)
    r.onsuccess = () => ok(r.result)
    r.onerror = () => ko(r.error)
  })
}
async function magasin<T>(mode: IDBTransactionMode, f: (s: IDBObjectStore) => IDBRequest): Promise<T> {
  const db = await ouvrir()
  return new Promise<T>((ok, ko) => {
    const q = f(db.transaction(MAGASIN, mode).objectStore(MAGASIN))
    q.onsuccess = () => { db.close(); ok(q.result as T) }
    q.onerror = () => { db.close(); ko(q.error) }
  })
}
const lire = <T>(cle: string) => magasin<T | undefined>('readonly', (s) => s.get(cle))
const ecrire = (cle: string, v: unknown) => magasin('readwrite', (s) => s.put(v, cle))

interface Local { patients: Element[]; analyses: Element[]; lesions: Element[]; prochain: number }
const local: Local = { patients: [], analyses: [], lesions: [], prochain: BASE_LOCALE }
const urls = new Map<string, string>()
const persister = () => ecrire('etat', local)

/** Efface tout ce que le visiteur a créé dans ce navigateur. */
export async function effacerLocal(): Promise<void> {
  await magasin('readwrite', (s) => s.clear())
  location.assign('/analyses/nouvelle')
}

/** Image d'une analyse du visiteur (null pour un cas de l'instantané). */
export const urlLocale = (id: number, nature: string) => urls.get(`${id}_${nature}`) ?? null

type Suivi = { id: number; cree_le: string; p_melanome: number; niveau: string; abcd: Record<string, Record<string, unknown>> | null }
const RANG: Record<string, number> = { faible: 0, renvoi: 1, eleve: 2, urgent: 3 }

/** Signaux d'évolution entre deux analyses (portage de engine/suivi.py). */
function comparer(avant: Suivi, apres: Suivi) {
  const signaux: Record<string, unknown>[] = []
  const r3 = (x: number) => Math.round(x * 1000) / 1000
  const dp = apres.p_melanome - avant.p_melanome
  if (dp >= 0.1) signaux.push({ code: 'p_mel_hausse', de: r3(avant.p_melanome), a: r3(apres.p_melanome) })
  if ((RANG[apres.niveau] ?? 0) > (RANG[avant.niveau] ?? 0)) signaux.push({ code: 'orientation_aggravee', de: avant.niveau, a: apres.niveau })
  const a0 = avant.abcd ?? {}, a1 = apres.abcd ?? {}
  if (a0.A && a1.A) {
    if (Number(a1.A.score) > Number(a0.A.score)) signaux.push({ code: 'asymetrie_hausse', de: a0.A.score, a: a1.A.score })
    if (Number(a1.B.score) - Number(a0.B.score) >= 2) signaux.push({ code: 'bords_hausse', de: a0.B.score, a: a1.B.score })
    const c0 = a0.C.couleurs as string[], c1 = a1.C.couleurs as string[]
    const nouvelles = c1.filter((c) => !c0.includes(c)).sort()
    if (nouvelles.length) signaux.push({ code: 'nouvelles_couleurs', couleurs: nouvelles })
    const d0 = a0.D?.mm as number | null, d1 = a1.D?.mm as number | null
    if (d0 != null && d1 != null && d1 - d0 >= 1) signaux.push({ code: 'diametre_hausse', de: d0, a: d1 })
  }
  const jours = Math.floor((new Date(apres.cree_le).getTime() - new Date(avant.cree_le).getTime()) / 86_400_000)
  return { analyse_precedente: avant.id, depuis: avant.cree_le, jours, delta_p_melanome: r3(dp), signaux, notable: signaux.length > 0 }
}

/** Ajoute une analyse du visiteur aux listes de l'instantané (création, ou relecture au chargement). */
function integrer(d: Instantane, a: Element) {
  d.analyses.unshift(a)
  const pid = String(a.patient_id)
  const p = d.patients.find((x) => x.id === a.patient_id)
  if (p) Object.assign(p, { nb_analyses: Number(p.nb_analyses) + 1, derniere_analyse: a.cree_le, dernier_statut: a.statut })
  const maj = { derniere_analyse: a.cree_le, dernier_niveau: a.niveau, derniere_image: a.id,
    evolution_notable: !!(a.evolution as { notable?: boolean } | null)?.notable }
  const les = (d.lesions[pid] ?? []) as Element[]
  const l = les.find((x) => x.id === a.lesion_id)
  if (l) Object.assign(l, maj, { nb_analyses: Number(l.nb_analyses) + 1 })
  const detail = d.details[String(a.lesion_id)]
  if (detail) {
    detail.ids.push(a.id)
    if (l) detail.lesion = { ...l }
  }
  const tb = d.tableau as { total_analyses: number; analyses_30j: number; par_statut: Record<string, number>; revues_en_attente: number }
  tb.total_analyses++; tb.analyses_30j++
  tb.par_statut[String(a.statut)] = (tb.par_statut[String(a.statut)] ?? 0) + 1
  if (a.revue === 'en_attente') tb.revues_en_attente++
}

async function restaurer(d: Instantane) {
  let etat: Local | undefined
  try { etat = await lire<Local>('etat') } catch { return }      // stockage indisponible : démonstration sans mémoire
  if (!etat) return
  local.prochain = etat.prochain
  for (const p of etat.patients) { local.patients.push(p); d.patients.unshift({ ...p, nb_analyses: 0 }) }
  for (const l of etat.lesions) {
    local.lesions.push(l)
    ;(d.lesions[String(l.patient_id)] ??= []).push({ ...l, nb_analyses: 0 })
    d.details[String(l.id)] = { lesion: { ...l }, patient_code: String(l.patient_code), ids: [], defaut: null, paires: {} }
  }
  for (const a of [...etat.analyses].reverse()) {
    local.analyses.unshift(a)
    integrer(d, a)
    for (const n of ['image', 'gradcam', 'abcd']) {
      const b = await lire<Blob>(`${a.id}_${n}`)
      if (b) urls.set(`${a.id}_${n}`, URL.createObjectURL(b))
    }
  }
}

async function creerAnalyse(d: Instantane, f: FormData): Promise<Element> {
  const { analyserImage } = await chargerMoteur()
  const pid = Number(f.get('patient_id'))
  const p = d.patients.find((x) => x.id === pid)
  if (!p) throw new RefusDemo(404, t('demo.introuvable'))
  const idLesion = Number(f.get('lesion_id')) || null
  let lesion = idLesion ? (d.lesions[String(pid)] as Element[]).find((l) => l.id === idLesion) ?? null : null
  let localisation = String(f.get('localisation') ?? 'unknown')
  if (lesion && localisation === 'unknown') localisation = String(lesion.localisation)
  const champAge = f.get('age')
  const annee = p.annee_naissance as number | null
  const age = champAge ? Number(champAge) : annee ? new Date().getFullYear() - annee : null
  const sexe = String(f.get('sexe') || p.sexe)
  const image = f.get('image') as File
  const id = local.prochain++
  const contexte = { age, sexe, localisation }
  const rapport = Number((d.parametres as { rapport_cout_defaut: number }).rapport_cout_defaut)
  let r
  try {
    r = await analyserImage(image, contexte, rapport, f.get('forcer') === 'true', String(id), surProgres ?? undefined)
  } catch (e) {
    const code = (e as { code?: string }).code
    if (code === 'illisible' || code === 'trop_petite') throw new RefusDemo(422, t('demo.imageIllisible'))
    console.error(e)
    throw new RefusDemo(422, t('demo.moteurIndisponible'))
  } finally {
    surProgres?.(null)
  }
  if (r.refus) throw new RefusDemo(422, t('hs.titre'), { code: 'image_hors_sujet', score: r.score, seuil: r.seuil })
  const cree_le = new Date().toISOString()
  if (!lesion) {
    const voisines = (d.lesions[String(pid)] ?? []) as Element[]
    const numero = voisines.reduce((m, l) => Math.max(m, Number(l.numero)), 0) + 1
    lesion = { id: local.prochain++, patient_id: pid, numero, nom: null, localisation, cree_le, notes: null, nb_analyses: 0,
      derniere_analyse: null, dernier_niveau: null, derniere_image: null, evolution_notable: false, patient_code: p.code }
    local.lesions.push(lesion)
    ;(d.lesions[String(pid)] ??= []).push({ ...lesion })
    d.details[String(lesion.id)] = { lesion: { ...lesion }, patient_code: String(p.code), ids: [], defaut: null, paires: {} }
  }
  const moi = d.moi as { nom_complet: string }
  const a: Element = {
    id, uid: crypto.randomUUID(), patient_id: pid, patient_code: p.code, auteur: moi.nom_complet, cree_le, age, sexe: sexe || 'unknown',
    localisation, modele: r.modele, version_modele: r.version, profil: r.profil, rapport_cout: r.rapport_cout, seuil_melanome: r.seuil_melanome,
    probabilites: r.probabilites, decision: r.decision, p_melanome: r.p_melanome, ensemble_conforme: r.ensemble_conforme, traite: r.traite,
    statut: r.statut, niveau: r.niveau, titre: '', message: '', avertissements: r.avertissements, duree_ms: r.duree_ms, revue: 'en_attente',
    diagnostic_final: null, commentaire: null, histologie: false, relecteur: null, revue_le: null, lesion_id: lesion.id,
    lesion_numero: lesion.numero, lesion_nom: lesion.nom, abcd: r.abcd, score_hors_sujet: r.score_hors_sujet,
    hors_sujet_force: r.hors_sujet, evolution: null, calibration: 'origine',
  }
  const precedente = d.analyses.find((x) => x.lesion_id === lesion!.id)
  if (precedente) {
    const evo = comparer(precedente as unknown as Suivi, a as unknown as Suivi)
    a.evolution = evo
    if (evo.notable) a.avertissements = [...(a.avertissements as unknown[]), { code: 'evolution', depuis: evo.depuis }]
  }
  for (const [n, b] of Object.entries(r.images)) {
    urls.set(`${id}_${n}`, URL.createObjectURL(b))
    await ecrire(`${id}_${n}`, b).catch(() => undefined)
  }
  await ecrire(`fichier_${id}`, image).catch(() => undefined)
  local.analyses.unshift(a)
  integrer(d, a)
  await persister().catch(() => undefined)
  return a
}

let instantane: Instantane | null = null
let chargement: Promise<Instantane> | null = null

function charger(): Promise<Instantane> {
  chargement ??= fetch('/demo/donnees.json').then((r) => r.json()).then(async (d: Instantane) => {
    await restaurer(d)
    instantane = d
    return d
  })
  return chargement
}

const connecte = () => { try { return sessionStorage.getItem(SESSION) === '1' } catch { return false } }
function definirSession(valeur: boolean) {
  try { if (valeur) sessionStorage.setItem(SESSION, '1'); else sessionStorage.removeItem(SESSION) } catch { /* session non mémorisée */ }
}

function page(liste: Element[], params: URLSearchParams, taille = TAILLE_PAGE) {
  const n = Math.max(Number(params.get('page') ?? 1), 1)
  const t2 = Number(params.get('taille') ?? taille)
  return { total: liste.length, elements: liste.slice((n - 1) * t2, n * t2) }
}

function trouver(liste: Element[], id: string): Element {
  const e = liste.find((x) => x.id === Number(id))
  if (!e) throw new RefusDemo(404, t('demo.introuvable'))
  return e
}

/** Compte rendu PDF pré-généré ? (cas présentés en détail seulement) */
export const pdfDisponible = (id: number) => instantane?.pdf.includes(id) ?? false

export async function repondreDemo<T>(methode: string, chemin: string, corps?: unknown): Promise<T> {
  const d = await charger()
  const url = new URL(chemin, 'http://demo')
  const parties = url.pathname.replace(/^\/api\//, '').split('/')
  const p = url.searchParams

  if (methode === 'POST' && chemin === '/api/connexion') { definirSession(true); return d.moi as T }
  if (methode === 'POST' && chemin === '/api/deconnexion') { definirSession(false); return { ok: true } as T }
  if (methode === 'POST' && chemin === '/api/analyses') return await creerAnalyse(d, corps as FormData) as unknown as T
  if (methode === 'POST' && chemin === '/api/patients') {
    const c = corps as Record<string, unknown>
    const id = local.prochain++
    const p: Element = { id, code: `P-LOCAL-${String(local.patients.length + 1).padStart(3, '0')}`, reference_externe: c.reference_externe ?? null,
      annee_naissance: c.annee_naissance ?? null, sexe: c.sexe ?? 'unknown', notes: c.notes ?? null, cree_le: new Date().toISOString(),
      nb_analyses: 0, derniere_analyse: null, dernier_statut: null }
    local.patients.push(p)
    d.patients.unshift({ ...p })
    await persister().catch(() => undefined)
    return p as unknown as T
  }
  if (methode === 'POST' && parties[0] === 'analyses' && parties[2] === 'revue' && Number(parties[1]) >= BASE_LOCALE) {
    const a = trouver(d.analyses, parties[1])
    const c = corps as { revue: string; diagnostic_final?: string | null; commentaire?: string | null; histologie?: boolean }
    Object.assign(a, { revue: c.revue, diagnostic_final: c.revue === 'corrigee' ? c.diagnostic_final : a.decision, commentaire: c.commentaire ?? null,
      histologie: !!c.histologie, relecteur: (d.moi as { nom_complet: string }).nom_complet, revue_le: new Date().toISOString() })
    ;(d.tableau as { revues_en_attente: number }).revues_en_attente--
    await persister().catch(() => undefined)
    return a as unknown as T
  }
  if (methode !== 'GET') throw new RefusDemo(403, t('demo.lectureSeule'))
  if (parties[0] === 'etat') return d.etat as T
  if (!connecte()) throw new RefusDemo(401, t('demo.lectureSeule'))

  const reponse = ((): unknown => {
    switch (parties[0]) {
      case 'moi': return d.moi
      case 'tableau-de-bord': return d.tableau
      case 'modele': return d.fiche
      case 'parametres': return d.parametres
      case 'utilisateurs': return d.utilisateurs
      case 'recalibrage': return d.recalibrage
      case 'sauvegardes': return d.sauvegardes
      case 'journal': return page(d.journal, p, 50)
      case 'patients': {
        if (!parties[1]) {
          const q = (p.get('q') ?? '').trim().toLowerCase()
          const liste = q ? d.patients.filter((x) => `${x.code} ${x.reference_externe ?? ''}`.toLowerCase().includes(q)) : d.patients
          return page(liste, p)
        }
        if (parties[2] === 'analyses') return d.analyses.filter((a) => a.patient_id === Number(parties[1]))
        if (parties[2] === 'lesions') return d.lesions[parties[1]] ?? []
        return trouver(d.patients, parties[1])
      }
      case 'lesions': {
        const l = d.details[parties[1]]
        if (!l) throw new RefusDemo(404, t('demo.introuvable'))
        const analyses = [...d.analyses.filter((a) => l.ids.includes(a.id))].sort((a, b) => l.ids.indexOf(a.id) - l.ids.indexOf(b.id))
        const a = Number(p.get('a')), b = Number(p.get('b'))
        const cle = `${Math.min(a, b)}-${Math.max(a, b)}`
        const paire = (x: Element, y: Element) => {
          const [av, ap] = new Date(String(x.cree_le)) > new Date(String(y.cree_le)) ? [y, x] : [x, y]
          return { avant: av.id, apres: ap.id, ...comparer(av as unknown as Suivi, ap as unknown as Suivi) }
        }
        const choisis = analyses.filter((x) => x.id === a || x.id === b)
        const comparaison = a && b && l.paires[cle] ? l.paires[cle]
          : a && b && choisis.length === 2 ? paire(choisis[0], choisis[1])
            : analyses.length >= 2 ? (l.ids.some((i) => i >= BASE_LOCALE) ? paire(analyses.at(-2)!, analyses.at(-1)!) : l.defaut) : null
        return { lesion: l.lesion, patient_code: l.patient_code, analyses, comparaison }
      }
      case 'analyses': {
        if (parties[1]) return trouver(d.analyses, parties[1])
        const statut = p.get('statut'), revue = p.get('revue')
        return page(d.analyses.filter((a) => (!statut || a.statut === statut) && (!revue || a.revue === revue)), p)
      }
      default: throw new RefusDemo(404, t('demo.introuvable'))
    }
  })()
  return reponse as T
}

/** « Et si » : calcul du modèle, disponible seulement s'il a été pré-calculé pour ce cas. */
export async function etSiDemo<T>(id: number, variable: string): Promise<T> {
  const d = await charger()
  if (id >= BASE_LOCALE) {
    const { etSiImage } = await chargerMoteur()
    const a = trouver(d.analyses, String(id))
    const fichier = await lire<Blob>(`fichier_${id}`)
    if (!fichier) throw new RefusDemo(422, t('demo.calculIndisponible'))
    return etSiImage<T>(fichier, { age: a.age as number | null, sexe: a.sexe as string, localisation: a.localisation as string }, variable as 'age', String(id))
  }
  const r = d.etsi[`${id}_${variable}`]
  if (!r) throw new RefusDemo(422, t('demo.calculIndisponible'))
  return r as T
}

// Vérification automatique du moteur du navigateur par rapport au moteur Python (outils/verifier_navigateur.py)
if (DEMO) {
  (window as unknown as Record<string, unknown>).__dermiaTest = chargerMoteur
}
