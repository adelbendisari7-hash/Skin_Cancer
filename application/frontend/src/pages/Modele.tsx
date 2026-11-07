import { useEffect, useState } from 'react'
import { api } from '../api'
import { Chargement, EnTete, Message, Panneau } from '../components/ui'
import { langueCourante, t, type Cle } from '../i18n'
import { liste, nombre, nomClasse, pourcent, statutModele } from '../lib/format'

interface Profil {
  experience: string
  architecture?: string
  calibre_sur: string
  thresholds: Record<string, number>
  conformal_q: number[]
  poids: { sha256: string }[]
  metriques_test: Mesures
  metriques_test_bcn?: Mesures
}
interface Mesures {
  decision_classique: Record<string, number>
  decision_cout_R10: Record<string, number>
  abstention: Record<string, number>
  n_images_test: number
  jeu?: string
}
interface Fiche {
  nom: string; version: string; date: string; description: string; statut: string; usage_prevu: string
  statut_i18n?: Record<string, string>
  i18n?: Record<string, Record<string, string | string[]>>
  donnees_entrainement: { jeu: string; licence: string; consequence: string; centres: string }
  pretraitement: { taille: number }
  classes: string[]; classes_malignes: string[]
  decision: { rapports_cout: number[]; rapport_defaut: number; regle: string }
  abstention: { methode: string; alpha: number; regle: string }
  hors_sujet?: { seuil: number; evaluation?: { rejet_validation?: number; rejet_test?: number; rejet_hors_sujet?: number; n_hors_sujet?: number } }
  profils: Record<string, Profil>
  limites: string[]
  peripherique: string
}

const LIGNES: [string, Cle, (v: number) => string][] = [
  ['F1 macro', 'mod.m.f1', (v) => nombre(v, 3)],
  ['Exactitude équilibrée', 'mod.m.bacc', (v) => nombre(v, 3)],
  ['AUC OvR macro', 'mod.m.auc', (v) => nombre(v, 3)],
  ['AUC mel', 'mod.m.aucMel', (v) => nombre(v, 3)],
  ['Sensibilité mel', 'mod.m.sens', (v) => pourcent(v)],
  ['Spécificité mel', 'mod.m.spec', (v) => pourcent(v)],
]
const RESEAUX: Record<string, string> = { efficientnet_b0: 'EfficientNet-B0', efficientnet_b2: 'EfficientNet-B2' }

export function Modele() {
  const [f, setF] = useState<Fiche | null>(null)
  const [erreur, setErreur] = useState<string | null>(null)
  useEffect(() => { api.fiche().then((x) => setF(x as unknown as Fiche)).catch((e) => setErreur(e.message)) }, [])
  if (erreur) return <Message>{erreur}</Message>
  if (!f) return <Chargement />
  // Textes du modèle : traduction fournie par le paquet du modèle si elle existe, sinon texte d'origine (français).
  const traduit = f.i18n?.[langueCourante()] ?? {}
  const tx = (champ: string, defaut: string) => (typeof traduit[champ] === 'string' ? traduit[champ] as string : defaut)
  const limites = Array.isArray(traduit.limites) ? traduit.limites : f.limites
  const profils = Object.entries(f.profils)
  const nomProfil = (k: string) => (k === 'complet' ? t('mod.profil.complet') : t('mod.profil.sans_contexte'))
  const archi = profils[0][1].architecture ?? 'efficientnet_b0'
  const ev = f.hors_sujet?.evaluation
  // Un tableau par jeu de test (le paquet v3 est mesuré séparément sur HAM10000 et sur BCN20000)
  const jeux = (['metriques_test', 'metriques_test_bcn'] as const).filter((j) => profils[0][1][j])
  const nomJeu = (m: Mesures) => (m.jeu ?? 'test HAM10000').replace(/^test /, '')

  return (
    <>
      <EnTete titre={t('nav.modele')} sousTitre={t('mod.sousTitre', {
        nom: f.nom, version: f.version, date: f.date, materiel: f.peripherique === 'cpu' ? t('mod.processeur') : t('mod.gpu'),
      })} />
      <div className="mb-6 rounded-lg border-s-4 border-renvoi bg-renvoi-pale px-5 py-4 text-[14px] text-renvoi">
        <p className="font-semibold">{statutModele(f.statut, f.statut_i18n)}</p>
        <p className="mt-1">{tx('consequence', f.donnees_entrainement.consequence)}</p>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Panneau titre={t('mod.ceQueFait')}>
          <p className="text-[14px]">{tx('description', f.description)}</p>
          <p className="mt-3 text-[14px]"><b>{t('mod.usage')}</b> {tx('usage_prevu', f.usage_prevu)}</p>
          <p className="mt-3 text-[14px]"><b>{t('mod.diagnostics')}</b> {liste(f.classes.map(nomClasse))}.{' '}
            {t('mod.malins', { liste: liste(f.classes_malignes.map(nomClasse)) })}</p>
          <p className="mt-3 text-[14px]"><b>{t('mod.architecture')}</b> {t('mod.architectureTexte', {
            reseau: RESEAUX[archi] ?? archi, taille: f.pretraitement.taille })}</p>
        </Panneau>
        <Panneau titre={t('mod.donnees')}>
          <dl className="grid grid-cols-[auto_1fr] gap-x-5 gap-y-2 text-[14px]">
            <dt className="text-encre-2">{t('mod.jeu')}</dt><dd>{f.donnees_entrainement.jeu}</dd>
            <dt className="text-encre-2">{t('mod.provenance')}</dt><dd>{tx('centres', f.donnees_entrainement.centres)}</dd>
            <dt className="text-encre-2">{t('mod.licence')}</dt><dd>{tx('licence', f.donnees_entrainement.licence)}</dd>
          </dl>
        </Panneau>
      </div>

      <Panneau titre={t('mod.perfs')} className="mt-6">
        <p className="mb-4 max-w-prose text-[14px] text-encre-2">{t('mod.perfsIntro', { n: profils[0][1].metriques_test.n_images_test })}</p>
        {jeux.map((j) => <PerformancesJeu key={j} mesures={profils.map(([k, p]) => [k, p[j]!] as [string, Mesures])}
          titre={jeux.length > 1 ? t('mod.jeuTest', { jeu: nomJeu(profils[0][1][j]!), n: profils[0][1][j]!.n_images_test }) : null}
          nomProfil={nomProfil} alpha={f.abstention.alpha} />)}
      </Panneau>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Panneau titre={t('mod.regles')}>
          <p className="text-[14px]"><b>{t('mod.prudence')}</b> {t('mod.prudenceTexte', {
            regle: tx('decision_regle', f.decision.regle), liste: f.decision.rapports_cout.join(', '), defaut: f.decision.rapport_defaut })}</p>
          <p className="mt-3 text-[14px]"><b>{t('mod.abst')}</b> {tx('abstention_methode', f.abstention.methode)}, α = {nombre(f.abstention.alpha, 2)} : {tx('abstention_regle', f.abstention.regle)}.</p>
          <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-5 gap-y-1 text-[13px] text-encre-2">
            {profils.map(([k, p]) => (
              <div key={k} className="contents"><dt>{nomProfil(k)}</dt>
                <dd>{t('mod.seuilsProfil', { liste: Object.entries(p.thresholds).map(([r, s]) => `R=${r} → ${nombre(s)}`).join(', '), jeu: tx(`calibre_sur_${k}`, p.calibre_sur) })}</dd></div>
            ))}
          </dl>
        </Panneau>
        <Panneau titre={t('mod.horsSujet')}>
          {f.hors_sujet ? <>
            <p className="text-[14px]">{t('mod.horsSujetTexte')}</p>
            {ev && <ul className="mt-3 flex flex-col gap-1 text-[14px]">
              {ev.rejet_test !== undefined && <li>{t('mod.hs.test', { v: pourcent(ev.rejet_test) })}</li>}
              {ev.rejet_hors_sujet !== undefined && <li>{t('mod.hs.ext', { v: pourcent(ev.rejet_hors_sujet), n: ev.n_hors_sujet ?? '?' })}</li>}
            </ul>}
          </> : <p className="text-[14px] text-encre-2">{t('mod.horsSujetAbsent')}</p>}
        </Panneau>
      </div>
      <Panneau titre={t('mod.limites')} className="mt-6">
        <ul className="flex list-disc flex-col gap-2 ps-5 text-[14px]">{limites.map((l) => <li key={l}>{l}</li>)}</ul>
      </Panneau>
      <p className="mt-6 text-[13px] break-all text-encre-2">
        {t('mod.integrite', { liste: profils.flatMap(([, p]) => p.poids.map((w) => w.sha256.slice(0, 16) + '…')).join(' ') })}
      </p>
    </>
  )
}

function PerformancesJeu({ mesures, titre, nomProfil, alpha }: {
  mesures: [string, Mesures][]; titre: string | null; nomProfil: (k: string) => string; alpha: number
}) {
  return (
    <div className="mb-6 last:mb-0">
      {titre && <h3 className="mb-2 text-[15px] font-semibold">{titre}</h3>}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[620px] text-start text-[14px]">
          <thead className="border-b border-trait text-[13px] text-encre-2">
            <tr><th className="py-2 pe-4 text-start font-semibold">{t('mod.mesure')}</th>
              {mesures.map(([k]) => <th key={k} colSpan={2} className="px-4 text-start font-semibold">{nomProfil(k)}</th>)}</tr>
            <tr className="text-[12px]"><th />
              {mesures.map(([k]) => [<th key={k + 'a'} className="px-4 py-1 text-start font-normal">{t('mod.classePlusProbable')}</th>,
                <th key={k + 'b'} className="px-4 py-1 text-start font-normal">{t('mod.reglePrudence')}</th>])}</tr>
          </thead>
          <tbody className="chiffres divide-y divide-trait-2">
            {LIGNES.map(([cle, libelle, fmt]) => (
              <tr key={cle}><td className="py-2 pe-4">{t(libelle)}</td>
                {mesures.map(([k, m]) => [
                  <td key={k + 'a'} className="px-4">{fmt(m.decision_classique[cle])}</td>,
                  <td key={k + 'b'} className="px-4">{fmt(m.decision_cout_R10[cle])}</td>])}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3 className="mt-6 mb-2 text-[15px] font-semibold">{t('mod.abstention')}</h3>
      <div className="grid gap-4 sm:grid-cols-2">
        {mesures.map(([k, m]) => {
          const ab = m.abstention
          return (
            <dl key={k} className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 rounded-[5px] border border-trait-2 px-4 py-3 text-[14px]">
              <dt className="col-span-2 mb-1 font-semibold">{nomProfil(k)}</dt>
              <dt className="text-encre-2">{t('mod.traites')}</dt><dd className="chiffres">{pourcent(ab.taux_traite, 0)}</dd>
              <dt className="text-encre-2">{t('mod.couverture', { c: pourcent(1 - alpha, 0) })}</dt><dd className="chiffres">{pourcent(ab['couverture'], 1)}</dd>
              <dt className="text-encre-2">{t('mod.couvMel')}</dt><dd className="chiffres">{pourcent(ab['couverture mel'], 1)}</dd>
              <dt className="text-encre-2">{t('mod.melSilence')}</dt><dd className="chiffres">{t('commun.surN', { a: ab.melanomes_manques_en_silence, b: ab.melanomes_test })}</dd>
              <dt className="text-encre-2">{t('mod.malinsOrientes')}</dt><dd className="chiffres">{pourcent(ab.sensibilite_malin_triage)}</dd>
            </dl>
          )
        })}
      </div>
    </div>
  )
}
