import type { Analyse, Niveau, Sexe, SignalEvolution } from '../api'
import { estCle, langueCourante, locale, t } from '../i18n'

// Codes HAM10000 (valeurs envoyées à l'API) ; les libellés viennent du dictionnaire de la langue active.
export const CODES_LOCALISATIONS = ['scalp', 'face', 'ear', 'neck', 'chest', 'abdomen', 'back', 'trunk', 'upper extremity',
  'hand', 'lower extremity', 'foot', 'genital', 'acral', 'unknown'] as const
export const CODES_CLASSES = ['nv', 'mel', 'bkl', 'bcc', 'akiec', 'vasc', 'df'] as const
export const CODES_SEXES: Sexe[] = ['female', 'male', 'unknown']

const libelle = (prefixe: string, code: string | null | undefined) => {
  const k = `${prefixe}.${code}`
  return estCle(k) ? t(k) : (code ?? '—')
}
export const nomLoc = (code: string | null | undefined) => libelle('loc', code)
export const nomClasse = (code: string | null | undefined) => libelle('classe', code)
export const nomSexe = (code: string | null | undefined) => libelle('sexe', code)
export const nomCouleur = (code: string) => libelle('couleur', code)
export const liste = (elements: string[]) => elements.join(t('commun.liste'))

export interface InfoNiveau { texte: string; fond: string; trait: string }

// Couleurs réservées au triage ; toujours accompagnées d'une icône et d'un libellé (jamais la couleur seule).
export const NIVEAUX: Record<Niveau, InfoNiveau> = {
  urgent: { texte: 'text-urgent', fond: 'bg-urgent-pale', trait: 'border-urgent' },
  eleve: { texte: 'text-avis', fond: 'bg-avis-pale', trait: 'border-avis' },
  renvoi: { texte: 'text-renvoi', fond: 'bg-renvoi-pale', trait: 'border-renvoi' },
  faible: { texte: 'text-benin', fond: 'bg-benin-pale', trait: 'border-benin' },
}
export const nomNiveau = (n: string) => libelle('niveau', n)
export const ORDRE_NIVEAU: Record<string, number> = { urgent: 0, eleve: 1, renvoi: 2, faible: 3 }

/** Titre et message d'orientation dans la langue active (le serveur les enregistre en français). */
export function triage(a: Pick<Analyse, 'statut' | 'decision' | 'titre' | 'message'>): { titre: string; message: string } {
  const kt = `tri.${a.statut}.titre`, km = `tri.${a.statut}.message`
  if (!estCle(kt) || !estCle(km)) return { titre: a.titre, message: a.message }
  return { titre: t(kt, { nom: nomClasse(a.decision) }), message: t(km) }
}

export const date = (iso: string | null | undefined) =>
  iso ? new Intl.DateTimeFormat(locale(), { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date(iso)) : '—'
export const dateHeure = (iso: string | null | undefined) =>
  iso ? new Intl.DateTimeFormat(locale(), { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
    .format(new Date(iso)) : '—'
export const pourcent = (p: number, decimales = 1) =>
  new Intl.NumberFormat(locale(), { style: 'percent', minimumFractionDigits: decimales, maximumFractionDigits: decimales }).format(p)
export const nombre = (x: number, decimales = 2) =>
  new Intl.NumberFormat(locale(), { minimumFractionDigits: decimales, maximumFractionDigits: decimales }).format(x)
export const entier = (x: number) => new Intl.NumberFormat(locale()).format(x)

/** Statut du modèle dans la langue active (traduction fournie par le modèle, sinon libellé connu). */
export function statutModele(statut?: string, traductions?: Partial<Record<string, string>> | null): string {
  const lg = langueCourante()
  if (traductions?.[lg]) return traductions[lg] as string
  if (statut?.startsWith('DÉMONSTRATION')) return t('statut.demo')
  return statut ?? ''
}

/** Texte d'un signal d'évolution entre deux analyses d'une même lésion. */
export function texteSignal(s: SignalEvolution): string {
  switch (s.code) {
    case 'p_mel_hausse': return t('evo.p_mel_hausse', { de: pourcent(Number(s.de)), a: pourcent(Number(s.a)) })
    case 'orientation_aggravee': return t('evo.orientation_aggravee', { de: nomNiveau(String(s.de)), a: nomNiveau(String(s.a)) })
    case 'nouvelles_couleurs': return t('evo.nouvelles_couleurs', { couleurs: liste((s.couleurs ?? []).map(nomCouleur)) })
    case 'diametre_hausse': return t('evo.diametre_hausse', { de: nombre(Number(s.de), 1), a: nombre(Number(s.a), 1) })
    default: {
      const k = `evo.${s.code}`
      return estCle(k) ? t(k, { de: String(s.de ?? ''), a: String(s.a ?? '') }) : s.code
    }
  }
}

export const ANNEE_COURANTE = new Date().getFullYear()

export function ageDepuis(annee: number | null): number | null {
  return annee ? ANNEE_COURANTE - annee : null
}
