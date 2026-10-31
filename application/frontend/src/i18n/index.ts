import { ar } from './ar'
import { en } from './en'
import { fr, type Cle } from './fr'

export type { Cle } from './fr'
export type Langue = 'fr' | 'en' | 'ar'

export const LANGUES: { code: Langue; nom: string }[] = [
  { code: 'fr', nom: 'Français' }, { code: 'en', nom: 'English' }, { code: 'ar', nom: 'العربية' },
]
const DICTIONNAIRES: Record<Langue, Record<Cle, string>> = { fr, en, ar }
// Chiffres latins en arabe (usage courant au Maghreb).
const LOCALES: Record<Langue, string> = { fr: 'fr-FR', en: 'en-GB', ar: 'ar-DZ-u-nu-latn' }
const STOCKAGE = 'dermia.langue'

function langueInitiale(): Langue {
  try {
    const l = localStorage.getItem(STOCKAGE)
    if (l === 'fr' || l === 'en' || l === 'ar') return l
  } catch { /* stockage indisponible : langue du navigateur */ }
  const nav = navigator.language.slice(0, 2)
  return nav === 'en' || nav === 'ar' ? nav : 'fr'
}

function appliquer(l: Langue) {
  document.documentElement.lang = l
  document.documentElement.dir = l === 'ar' ? 'rtl' : 'ltr'
}

let courante: Langue = langueInitiale()
appliquer(courante)

/** Langue active (lue au rendu : l'arbre est remonté à chaque changement de langue). */
export const langueCourante = (): Langue => courante
export const locale = (): string => LOCALES[courante]
export const estCle = (k: string): k is Cle => k in fr

/** Change la langue active, la mémorise et oriente la page (droite à gauche pour l'arabe). */
export function definirLangue(l: Langue): void {
  courante = l
  try { localStorage.setItem(STOCKAGE, l) } catch { /* préférence non mémorisée */ }
  appliquer(l)
}

/** Texte traduit ; les variables {nom} sont remplacées. */
export function t(cle: Cle, vars?: Record<string, string | number>): string {
  let s = DICTIONNAIRES[courante][cle] ?? fr[cle]
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, String(v))
  return s
}
