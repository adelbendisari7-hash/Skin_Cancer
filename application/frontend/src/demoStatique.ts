// Démonstration en ligne (construction Vercel, VITE_DEMO_STATIQUE=1) : l'interface lit un instantané des réponses
// réelles de l'API, exporté par outils/exporter_demo_statique.py. Aucun serveur, aucun calcul, aucune écriture.
// La version installée de l'application n'utilise jamais ce module.
import { t } from './i18n'

export const DEMO = import.meta.env.VITE_DEMO_STATIQUE === '1'
const SESSION = 'dermia.demo.connecte'
const TAILLE_PAGE = 25

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
  constructor(statut: number, message: string) {
    super(message)
    this.statut = statut
  }
}

let instantane: Instantane | null = null
let chargement: Promise<Instantane> | null = null

function charger(): Promise<Instantane> {
  chargement ??= fetch('/demo/donnees.json').then((r) => r.json()).then((d: Instantane) => { instantane = d; return d })
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
  if (!e) throw new RefusDemo(404, t('demo.lectureSeule'))
  return e
}

/** Compte rendu PDF pré-généré ? (cas présentés en détail seulement) */
export const pdfDisponible = (id: number) => instantane?.pdf.includes(id) ?? false

export async function repondreDemo<T>(methode: string, chemin: string): Promise<T> {
  const d = await charger()
  const url = new URL(chemin, 'http://demo')
  const parties = url.pathname.replace(/^\/api\//, '').split('/')
  const p = url.searchParams

  if (methode === 'POST' && chemin === '/api/connexion') { definirSession(true); return d.moi as T }
  if (methode === 'POST' && chemin === '/api/deconnexion') { definirSession(false); return { ok: true } as T }
  if (methode === 'POST' && parties[0] === 'analyses' && parties[2] === 'et-si') {
    throw new RefusDemo(422, t('demo.calculIndisponible'))
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
        if (!l) throw new RefusDemo(404, t('demo.lectureSeule'))
        const analyses = [...d.analyses.filter((a) => l.ids.includes(a.id))].sort((a, b) => l.ids.indexOf(a.id) - l.ids.indexOf(b.id))
        const a = Number(p.get('a')), b = Number(p.get('b'))
        const cle = `${Math.min(a, b)}-${Math.max(a, b)}`
        const comparaison = a && b ? (l.paires[cle] ?? l.defaut) : l.defaut
        return { lesion: l.lesion, patient_code: l.patient_code, analyses, comparaison }
      }
      case 'analyses': {
        if (parties[1]) return trouver(d.analyses, parties[1])
        const statut = p.get('statut'), revue = p.get('revue')
        return page(d.analyses.filter((a) => (!statut || a.statut === statut) && (!revue || a.revue === revue)), p)
      }
      default: throw new RefusDemo(404, t('demo.lectureSeule'))
    }
  })()
  return reponse as T
}

/** « Et si » : calcul du modèle, disponible seulement s'il a été pré-calculé pour ce cas. */
export async function etSiDemo<T>(id: number, variable: string): Promise<T> {
  const d = await charger()
  const r = d.etsi[`${id}_${variable}`]
  if (!r) throw new RefusDemo(422, t('demo.calculIndisponible'))
  return r as T
}
