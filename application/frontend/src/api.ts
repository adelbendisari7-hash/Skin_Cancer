// Client de l'API locale (même origine ; la session est un cookie HttpOnly).
import { DEMO, etSiDemo, RefusDemo, repondreDemo } from './demoStatique'
import { langueCourante, t, type Langue } from './i18n'

export type Role = 'admin' | 'medecin'
export type Sexe = 'male' | 'female' | 'unknown'
export type Niveau = 'urgent' | 'eleve' | 'renvoi' | 'faible'
export type Profil = 'complet' | 'sans_contexte'

export interface EtatModele {
  charge: boolean
  erreur?: string
  nom?: string
  version?: string
  statut?: string
  statut_i18n?: Partial<Record<Langue, string>> | null
  detection_hors_sujet?: boolean
  peripherique?: string
  localisations?: string[]
  classes?: string[]
  noms_classes?: Record<string, string>
  classes_malignes?: string[]
  rapports_cout?: number[]
}

export interface Etat {
  produit: string
  version: string
  installation_requise: boolean
  etablissement: string
  modele: EtatModele
}

export interface Utilisateur {
  id: number
  identifiant: string
  nom_complet: string
  role: Role
  actif: boolean
  cree_le: string
  derniere_connexion: string | null
}

export interface Patient {
  id: number
  code: string
  reference_externe: string | null
  annee_naissance: number | null
  sexe: Sexe
  notes: string | null
  cree_le: string
  nb_analyses: number
  derniere_analyse: string | null
  dernier_statut: string | null
}

/** Avertissement codé, traduit par l'interface (« texte » : ancien message libre en français). */
export interface Avertissement { code: string; texte?: string; largeur?: number; hauteur?: number; depuis?: string }

export interface MesureABCD {
  fiable: boolean
  alertes: string[]
  surface_relative?: number
  A: { score: number; indice_forme: number; ecart_couleur: number; axes_asymetriques: boolean[] } | null
  B: { score: number; secteurs_abrupts: boolean[]; intensites: number[]; irregularite: number } | null
  C: { score: number; couleurs: string[]; fractions: Record<string, number> } | null
  D: { mm: number | null; superieur_6mm: boolean | null } | null
}

export interface SignalEvolution { code: string; de?: number | string; a?: number | string; couleurs?: string[] }

export interface Evolution {
  analyse_precedente: number
  depuis: string
  jours: number | null
  delta_p_melanome: number
  signaux: SignalEvolution[]
  notable: boolean
}

export interface Analyse {
  id: number
  uid: string
  patient_id: number
  patient_code: string
  auteur: string
  cree_le: string
  age: number | null
  sexe: Sexe
  localisation: string
  modele: string
  version_modele: string
  profil: Profil
  rapport_cout: number
  seuil_melanome: number
  probabilites: Record<string, number>
  decision: string
  p_melanome: number
  ensemble_conforme: string[]
  traite: boolean
  statut: string
  niveau: Niveau
  titre: string
  message: string
  avertissements: Avertissement[]
  duree_ms: number
  revue: 'en_attente' | 'confirmee' | 'corrigee'
  diagnostic_final: string | null
  commentaire: string | null
  histologie: boolean
  relecteur: string | null
  revue_le: string | null
  lesion_id: number | null
  lesion_numero: number | null
  lesion_nom: string | null
  abcd: MesureABCD | null
  score_hors_sujet: number | null
  hors_sujet_force: boolean
  evolution: Evolution | null
  calibration: string
}

export interface Lesion {
  id: number
  patient_id: number
  numero: number
  nom: string | null
  localisation: string
  cree_le: string
  notes: string | null
  nb_analyses: number
  derniere_analyse: string | null
  dernier_niveau: Niveau | null
  derniere_image: number | null
  evolution_notable: boolean
}

export interface LesionDetail {
  lesion: Lesion
  patient_code: string
  analyses: Analyse[]
  comparaison: (Evolution & { avant: number; apres: number }) | null
}

export interface Page<T> { total: number; elements: T[] }

export interface TableauDeBord {
  total_analyses: number
  analyses_30j: number
  patients: number
  par_statut: Record<string, number>
  revues_en_attente: number
  taux_accord: number | null
  par_jour: { jour: string; n: number }[]
}

export interface EtSiReponse {
  variable: 'age' | 'localisation'
  actuel: number | string | null
  serie: { valeur: number | string; p_melanome: number }[]
  seuil_melanome: number
}

export interface EntreeJournal {
  id: number
  le: string
  utilisateur: string | null
  action: string
  objet: string | null
  objet_id: string | null
  details: Record<string, unknown> | null
}

export interface Parametres { nom_etablissement: string; rapport_cout_defaut: number; champ_dermoscope_mm: number | null }

export interface EvaluationSeuils {
  couverture: number
  couverture_mel: number | null
  taux_traite: number
  mel_manques_en_silence: number
}

export interface Calibration {
  id: number
  cree_le: string
  auteur: string | null
  profil: Profil
  active: boolean
  applique_le: string | null
  parametres: { thresholds: Record<string, number>; conformal_q: number[]; sources_q: string[]; source_seuil: string }
  resume: {
    n: number
    n_par_classe: Record<string, number>
    sources_q: Record<string, string>
    source_seuil: string
    seuil_mel: { origine: number; propose: number }
    alpha: number
    rapport_cout: number
    origine: EvaluationSeuils
    recalibre_validation_croisee?: EvaluationSeuils
    histologie_seulement?: boolean
    recommandation?: { decision: 'appliquer' | 'conserver'; raison: string }
  }
}

export interface EtatRecalibrage {
  modele: string
  version: string
  minimum_par_classe: number
  minimum_proposition: number
  profils: Record<Profil, {
    n_valides: number
    n_histologie: number
    par_classe: Record<string, number>
    active: Calibration | null
    propositions: Calibration[]
    origine: { thresholds: Record<string, number>; conformal_q: number[] }
  }>
}

export interface Sauvegarde {
  nom: string
  taille: number
  type: string
  date?: string
  version?: string
  n_patients?: number
  n_analyses?: number
  n_utilisateurs?: number
  n_images?: number
}

export class ErreurApi extends Error {
  readonly statut: number
  readonly code?: string
  readonly details?: Record<string, unknown>
  constructor(statut: number, message: string, details?: Record<string, unknown>) {
    super(message)
    this.statut = statut
    this.details = details
    this.code = typeof details?.code === 'string' ? details.code : undefined
  }
}

function messageErreur(corps: unknown, statut: number): string {
  const d = (corps as { detail?: unknown })?.detail
  if (typeof d === 'string') return d
  if (d && typeof d === 'object' && !Array.isArray(d) && typeof (d as { message?: unknown }).message === 'string') {
    return (d as { message: string }).message
  }
  if (Array.isArray(d)) {
    // erreurs de validation Pydantic : on garde le premier message lisible
    const e = d[0] as { msg?: string; loc?: string[] }
    return e?.msg ? t('commun.champInvalide', { champ: String(e.loc?.at(-1) ?? ''), msg: e.msg }) : t('commun.donneesInvalides')
  }
  if (statut === 0) return t('commun.serveurInjoignable')
  return t('commun.erreurStatut', { statut })
}

async function demo<T>(appel: () => Promise<T>): Promise<T> {
  try {
    return await appel()
  } catch (e) {
    throw e instanceof RefusDemo ? new ErreurApi(e.statut, e.message) : e
  }
}

async function requete<T>(methode: string, chemin: string, corps?: unknown): Promise<T> {
  if (DEMO) return demo(() => repondreDemo<T>(methode, chemin))
  let r: Response
  const entetes: Record<string, string> = { 'X-Langue': langueCourante() }
  if (corps !== undefined && !(corps instanceof FormData)) entetes['Content-Type'] = 'application/json'
  try {
    r = await fetch(chemin, {
      method: methode,
      credentials: 'same-origin',
      headers: entetes,
      body: corps instanceof FormData ? corps : corps === undefined ? undefined : JSON.stringify(corps),
    })
  } catch {
    throw new ErreurApi(0, messageErreur(null, 0))
  }
  const texte = await r.text()
  let json: unknown = null
  try { json = texte ? JSON.parse(texte) : null } catch { json = null }
  if (!r.ok) {
    const d = (json as { detail?: unknown })?.detail
    throw new ErreurApi(r.status, messageErreur(json, r.status),
      d && typeof d === 'object' && !Array.isArray(d) ? d as Record<string, unknown> : undefined)
  }
  return json as T
}

type DonneesPatient = { annee_naissance: number | null; sexe: Sexe; reference_externe: string | null; notes: string | null }

export const api = {
  etat: () => requete<Etat>('GET', '/api/etat'),
  installer: (d: { identifiant: string; nom_complet: string; mot_de_passe: string; nom_etablissement: string }) =>
    requete<{ ok: boolean }>('POST', '/api/installation', d),
  connexion: (identifiant: string, mot_de_passe: string) =>
    requete<Utilisateur>('POST', '/api/connexion', { identifiant, mot_de_passe }),
  deconnexion: () => requete<{ ok: boolean }>('POST', '/api/deconnexion'),
  moi: () => requete<Utilisateur>('GET', '/api/moi'),
  changerMotDePasse: (ancien: string, nouveau: string) =>
    requete<{ ok: boolean }>('POST', '/api/moi/mot-de-passe', { ancien, nouveau }),

  tableauDeBord: () => requete<TableauDeBord>('GET', '/api/tableau-de-bord'),

  patients: (q = '', page = 1) =>
    requete<Page<Patient>>('GET', `/api/patients?q=${encodeURIComponent(q)}&page=${page}`),
  patient: (id: number) => requete<Patient>('GET', `/api/patients/${id}`),
  creerPatient: (d: DonneesPatient) => requete<Patient>('POST', '/api/patients', d),
  modifierPatient: (id: number, d: DonneesPatient) => requete<Patient>('PATCH', `/api/patients/${id}`, d),
  analysesDuPatient: (id: number) => requete<Analyse[]>('GET', `/api/patients/${id}/analyses`),
  lesionsDuPatient: (id: number) => requete<Lesion[]>('GET', `/api/patients/${id}/lesions`),
  lesion: (id: number, a?: number, b?: number) =>
    requete<LesionDetail>('GET', `/api/lesions/${id}${a && b ? `?a=${a}&b=${b}` : ''}`),
  modifierLesion: (id: number, d: { nom?: string | null; notes?: string | null }) =>
    requete<Lesion>('PATCH', `/api/lesions/${id}`, d),

  analyses: (f: { statut?: string; revue?: string; page?: number; taille?: number } = {}) => {
    const p = new URLSearchParams()
    Object.entries(f).forEach(([k, v]) => v !== undefined && v !== '' && p.set(k, String(v)))
    return requete<Page<Analyse>>('GET', `/api/analyses?${p}`)
  },
  analyse: (id: number) => requete<Analyse>('GET', `/api/analyses/${id}`),
  creerAnalyse: (form: FormData) => requete<Analyse>('POST', '/api/analyses', form),
  etSi: (id: number, variable: 'age' | 'localisation') => (DEMO ? demo(() => etSiDemo<EtSiReponse>(id, variable))
    : requete<EtSiReponse>('POST', `/api/analyses/${id}/et-si`, { variable })),
  revue: (id: number, d: { revue: 'confirmee' | 'corrigee'; diagnostic_final?: string | null; commentaire?: string | null; histologie?: boolean }) =>
    requete<Analyse>('POST', `/api/analyses/${id}/revue`, d),
  imageUrl: (id: number, nature: 'image' | 'gradcam' | 'abcd') =>
    (DEMO ? `/demo/images/${id}_${nature}.jpg` : `/api/analyses/${id}/image/${nature}`),
  compteRenduUrl: (id: number, langue: Langue) =>
    (DEMO ? `/demo/pdf/${id}_${langue}.pdf` : `/api/analyses/${id}/compte-rendu.pdf?langue=${langue}`),

  fiche: () => requete<Record<string, unknown>>('GET', '/api/modele'),
  parametres: () => requete<Parametres>('GET', '/api/parametres'),
  ecrireParametres: (d: Partial<Parametres>) => requete<Parametres>('PUT', '/api/parametres', d),
  utilisateurs: () => requete<Utilisateur[]>('GET', '/api/utilisateurs'),
  creerUtilisateur: (d: { identifiant: string; nom_complet: string; role: Role; mot_de_passe: string }) =>
    requete<Utilisateur>('POST', '/api/utilisateurs', d),
  modifierUtilisateur: (id: number, d: Partial<{ nom_complet: string; role: Role; actif: boolean; mot_de_passe: string }>) =>
    requete<Utilisateur>('PATCH', `/api/utilisateurs/${id}`, d),
  journal: (page = 1) => requete<Page<EntreeJournal>>('GET', `/api/journal?page=${page}`),

  recalibrage: () => requete<EtatRecalibrage>('GET', '/api/recalibrage'),
  proposerRecalibrage: (profil: Profil, histologie_seulement: boolean) =>
    requete<Calibration>('POST', '/api/recalibrage/propositions', { profil, histologie_seulement }),
  appliquerRecalibrage: (id: number) => requete<Calibration>('POST', `/api/recalibrage/${id}/appliquer`),
  reinitialiserRecalibrage: (profil: Profil) => requete<{ ok: boolean }>('POST', `/api/recalibrage/reinitialiser/${profil}`),

  sauvegardes: () => requete<Sauvegarde[]>('GET', '/api/sauvegardes'),
  creerSauvegarde: () => requete<Sauvegarde>('POST', '/api/sauvegardes'),
  supprimerSauvegarde: (nom: string) => requete<{ ok: boolean }>('DELETE', `/api/sauvegardes/${encodeURIComponent(nom)}`),
  restaurerSauvegarde: (nom: string) => requete<Record<string, unknown>>('POST', `/api/sauvegardes/${encodeURIComponent(nom)}/restaurer`),
  importerSauvegarde: (f: File) => {
    const fd = new FormData()
    fd.set('fichier', f)
    return requete<{ nom: string }>('POST', '/api/sauvegardes/importer', fd)
  },
  urlSauvegarde: (nom: string) => `/api/sauvegardes/${encodeURIComponent(nom)}`,
}
