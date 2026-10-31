// Interface entre la page et le fil de calcul (démonstration en ligne uniquement).
import type { Contexte } from './travail'

export type { Contexte }
export interface Progres { etape: 'telechargement' | 'calcul'; part: number }

let fil: Worker | null = null
let suivant = 1
const attentes = new Map<number, { ok: (v: unknown) => void; ko: (e: Error) => void; progres?: (p: Progres) => void }>()

function travailleur(): Worker {
  if (fil) return fil
  fil = new Worker(new URL('./travail.ts', import.meta.url), { type: 'module' })
  fil.onmessage = (e: MessageEvent) => {
    const { id, type } = e.data
    const a = attentes.get(id)
    if (!a) return
    if (type === 'progres') { a.progres?.({ etape: e.data.etape, part: e.data.part }); return }
    attentes.delete(id)
    if (type === 'fini') a.ok(e.data.donnees)
    else a.ko(Object.assign(new Error(e.data.message), { code: e.data.code }))
  }
  // Fil impossible à charger : on rejette tout ce qui attend, plutôt que de laisser la page bloquée
  fil.onerror = (e) => {
    for (const [id, x] of attentes) { attentes.delete(id); x.ko(new Error(e.message || 'fil de calcul indisponible')) }
    fil = null
  }
  return fil
}

function demander<T>(message: Record<string, unknown>, progres?: (p: Progres) => void): Promise<T> {
  const id = suivant++
  return new Promise<T>((ok, ko) => {
    attentes.set(id, { ok: ok as (v: unknown) => void, ko, progres })
    travailleur().postMessage({ id, ...message })
  })
}

export interface ResultatNavigateur {
  refus: boolean; score?: number; seuil?: number
  profil: 'complet' | 'sans_contexte'; probabilites: Record<string, number>; decision: string; p_melanome: number
  seuil_melanome: number; rapport_cout: number; ensemble_conforme: string[]; traite: boolean; statut: string
  niveau: 'urgent' | 'eleve' | 'renvoi' | 'faible'; avertissements: Record<string, unknown>[]; modele: string; version: string
  duree_ms: number; abcd: unknown; score_hors_sujet: number; hors_sujet: boolean
  images: { image: Blob; gradcam: Blob; abcd: Blob }
}

export const analyserImage = (fichier: Blob, contexte: Contexte, rapport: number | null, forcer: boolean, cle: string, progres?: (p: Progres) => void) =>
  demander<ResultatNavigateur>({ type: 'analyser', fichier, contexte, rapport, forcer, cle }, progres)

export const etSiImage = <T>(fichier: Blob, contexte: Contexte, variable: 'age' | 'localisation', cle: string) =>
  demander<T>({ type: 'etsi', fichier, contexte, variable, cle })

export const abcdImage = <T>(fichier: Blob, champ: number | null) => demander<T>({ type: 'abcd', fichier, champ })
