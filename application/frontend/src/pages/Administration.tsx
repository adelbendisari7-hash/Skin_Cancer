import { Archive, CircleCheck, DatabaseBackup, Download, RotateCcw, Scale, ShieldAlert, Trash2, Upload, UserPlus } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  api, type Calibration, type EntreeJournal, type EtatRecalibrage, type EvaluationSeuils, type Page, type Parametres, type Profil,
  type Role, type Sauvegarde, type Utilisateur,
} from '../api'
import { Bouton, Champ, Chargement, Confirmation, Dialogue, EnTete, Liste, Message, Panneau, Saisie } from '../components/ui'
import { useApp } from '../contexte'
import { DEMO } from '../demoStatique'
import { estCle, t } from '../i18n'
import { CODES_CLASSES, dateHeure, entier, liste, nombre, nomClasse, pourcent } from '../lib/format'

type Retour = { type: 'erreur' | 'info'; texte: string } | null

function NouveauCompte({ onFini }: { onFini: () => void }) {
  const [f, setF] = useState({ identifiant: '', nom_complet: '', role: 'medecin' as Role, mot_de_passe: '' })
  const [erreur, setErreur] = useState<string | null>(null)
  async function envoyer(e: FormEvent) {
    e.preventDefault(); setErreur(null)
    try { await api.creerUtilisateur(f); onFini() } catch (err) { setErreur((err as Error).message) }
  }
  return (
    <form onSubmit={envoyer} className="flex flex-col gap-4">
      {erreur && <Message>{erreur}</Message>}
      <Champ label={t('adm.nom')}>{(id) => <Saisie id={id} value={f.nom_complet} onChange={(e) => setF({ ...f, nom_complet: e.target.value })} required minLength={2} />}</Champ>
      <Champ label={t('acces.identifiant')}>{(id) => <Saisie id={id} value={f.identifiant} onChange={(e) => setF({ ...f, identifiant: e.target.value })} required pattern="[A-Za-z0-9._\-]{3,64}" />}</Champ>
      <Champ label={t('adm.role')}>{(id) => (
        <Liste id={id} value={f.role} onChange={(e) => setF({ ...f, role: e.target.value as Role })}>
          <option value="medecin">{t('role.medecin')}</option><option value="admin">{t('role.admin')}</option>
        </Liste>)}
      </Champ>
      <Champ label={t('adm.mdpProvisoire')} aide={t('adm.mdpProvisoireAide')}>
        {(id) => <Saisie id={id} type="text" value={f.mot_de_passe} onChange={(e) => setF({ ...f, mot_de_passe: e.target.value })} required minLength={10} />}
      </Champ>
      <Bouton type="submit" className="self-start">{t('adm.creerCompte')}</Bouton>
    </form>
  )
}

function Comptes() {
  const { utilisateur } = useApp()
  const [listeU, setListe] = useState<Utilisateur[] | null>(null)
  const [creation, setCreation] = useState(false)
  const [erreur, setErreur] = useState<string | null>(null)
  const charger = () => api.utilisateurs().then(setListe).catch((e) => setErreur(e.message))
  useEffect(() => { void charger() }, [])
  async function basculer(u: Utilisateur) {
    try { await api.modifierUtilisateur(u.id, { actif: !u.actif }); await charger() } catch (e) { setErreur((e as Error).message) }
  }
  async function reinitialiser(u: Utilisateur) {
    const mdp = window.prompt(t('adm.promptMdp', { nom: u.nom_complet }))
    if (!mdp) return
    try { await api.modifierUtilisateur(u.id, { mot_de_passe: mdp }); setErreur(null) } catch (e) { setErreur((e as Error).message) }
  }
  return (
    <Panneau titre={t('adm.comptes')} actions={<Bouton variante="secondaire" onClick={() => setCreation(true)} icone={<UserPlus className="size-4" aria-hidden />}>{t('adm.ajouter')}</Bouton>}>
      {erreur && <div className="mb-3"><Message>{erreur}</Message></div>}
      {!listeU ? <Chargement /> : (
        <ul className="-mx-5 divide-y divide-trait-2">
          {listeU.map((u) => (
            <li key={u.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-3">
              <div>
                <p className="font-semibold">{u.nom_complet} {!u.actif && <span className="font-normal text-encre-2">{t('adm.desactive')}</span>}</p>
                <p className="text-[13px] text-encre-2">{t('adm.infoCompte', {
                  identifiant: u.identifiant, role: (u.role === 'admin' ? t('role.admin') : t('role.medecin')).toLowerCase(),
                  date: dateHeure(u.derniere_connexion),
                })}</p>
              </div>
              {u.id !== utilisateur?.id && (
                <div className="flex gap-2">
                  <Bouton variante="discret" onClick={() => reinitialiser(u)}>{t('adm.reinitMdp')}</Bouton>
                  <Bouton variante={u.actif ? 'danger' : 'secondaire'} onClick={() => basculer(u)}>{u.actif ? t('adm.desactiver') : t('adm.reactiver')}</Bouton>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      <Dialogue ouvert={creation} titre={t('adm.ajouter')} onFermer={() => setCreation(false)}>
        <NouveauCompte onFini={() => { setCreation(false); void charger() }} />
      </Dialogue>
    </Panneau>
  )
}

function Reglages() {
  const { etat, rafraichir } = useApp()
  const [f, setF] = useState<Parametres | null>(null)
  const [champ, setChamp] = useState('')
  const [message, setMessage] = useState<Retour>(null)
  useEffect(() => {
    api.parametres().then((p) => { setF(p); setChamp(p.champ_dermoscope_mm ? String(p.champ_dermoscope_mm) : '') }).catch(() => undefined)
  }, [])
  if (!f) return <Panneau titre={t('adm.reglages')}><Chargement /></Panneau>
  async function envoyer(e: FormEvent) {
    e.preventDefault()
    try {
      const p = await api.ecrireParametres({ nom_etablissement: f!.nom_etablissement, rapport_cout_defaut: f!.rapport_cout_defaut,
        champ_dermoscope_mm: champ.trim() === '' ? 0 : Number(champ.replace(',', '.')) })
      setF(p); await rafraichir(); setMessage({ type: 'info', texte: t('adm.enregistres') })
    } catch (err) { setMessage({ type: 'erreur', texte: (err as Error).message }) }
  }
  const niveau = (r: number) => (r === 5 ? t('adm.modere') : r === 10 ? t('adm.eleveRec') : t('adm.tresEleve'))
  return (
    <Panneau titre={t('adm.reglages')}>
      <form onSubmit={envoyer} className="flex max-w-lg flex-col gap-4">
        {message && <Message type={message.type}>{message.texte}</Message>}
        <Champ label={t('acces.nomEtablissement')}>{(id) => <Saisie id={id} value={f.nom_etablissement} onChange={(e) => setF({ ...f, nom_etablissement: e.target.value })} />}</Champ>
        <Champ label={t('adm.prudence')} aide={t('adm.prudenceAide')}>
          {(id) => (
            <Liste id={id} value={f.rapport_cout_defaut} onChange={(e) => setF({ ...f, rapport_cout_defaut: Number(e.target.value) })}>
              {(etat?.modele.rapports_cout ?? [5, 10, 20]).map((r) => <option key={r} value={r}>{t('adm.ratio', { niveau: niveau(r), r })}</option>)}
            </Liste>)}
        </Champ>
        <Champ label={t('adm.champ')} aide={t('adm.champAide')}>
          {(id) => <Saisie id={id} inputMode="decimal" value={champ} onChange={(e) => setChamp(e.target.value)} placeholder="—" className="max-w-[140px]" />}
        </Champ>
        <Bouton type="submit" className="self-start">{t('adm.enregistrer')}</Bouton>
      </form>
    </Panneau>
  )
}

function Journal() {
  const [page, setPage] = useState(1)
  const [d, setD] = useState<Page<EntreeJournal> | null>(null)
  useEffect(() => { api.journal(page).then(setD).catch(() => undefined) }, [page])
  const action = (a: string) => { const k = `action.${a}`; return estCle(k) ? t(k) : a }
  return (
    <Panneau titre={t('adm.ongletJournal')}>
      {!d ? <Chargement /> : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-start text-[13.5px]">
              <thead className="border-b border-trait text-encre-2"><tr><th className="py-2 pe-4 text-start font-semibold">{t('adm.date')}</th>
                <th className="pe-4 text-start font-semibold">{t('adm.utilisateur')}</th><th className="pe-4 text-start font-semibold">{t('adm.action')}</th>
                <th className="text-start font-semibold">{t('adm.objet')}</th></tr></thead>
              <tbody className="divide-y divide-trait-2">
                {d.elements.map((j) => (
                  <tr key={j.id}><td className="py-2 pe-4 whitespace-nowrap">{dateHeure(j.le)}</td><td className="pe-4">{j.utilisateur ?? '—'}</td>
                    <td className={`pe-4 ${['connexion_refusee', 'image_refusee'].includes(j.action) ? 'text-urgent' : ''}`}>{action(j.action)}</td>
                    <td className="text-encre-2" dir="ltr">{j.objet ? `${j.objet} ${j.objet_id ?? ''}` : ''}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3 flex items-center gap-3 text-[13.5px]">
            <Bouton variante="secondaire" disabled={page === 1} onClick={() => setPage(page - 1)}>{t('adm.plusRecents')}</Bouton>
            <Bouton variante="secondaire" disabled={page * 50 >= d.total} onClick={() => setPage(page + 1)}>{t('adm.plusAnciens')}</Bouton>
            <span className="text-encre-2">{t('adm.entrees', { n: entier(d.total) })}</span>
          </div>
        </>
      )}
    </Panneau>
  )
}

// ---- recalibrage local -------------------------------------------------------------------------

function TableauProposition({ c, alpha }: { c: Calibration; alpha: number }) {
  const r = c.resume
  const o = r.origine, v = r.recalibre_validation_croisee
  const lignes: [string, (e: EvaluationSeuils) => string][] = [
    [t('rec.couverture', { c: pourcent(1 - alpha, 0) }), (e) => pourcent(e.couverture)],
    [t('rec.couvMel'), (e) => (e.couverture_mel === null ? '—' : pourcent(e.couverture_mel))],
    [t('rec.traites'), (e) => pourcent(e.taux_traite, 0)],
    [t('rec.melSilence'), (e) => entier(e.mel_manques_en_silence)],
  ]
  const recal = CODES_CLASSES.filter((k) => r.sources_q[k] === 'locale').map(nomClasse)
  return (
    <div className="flex flex-col gap-2">
      <div className="overflow-x-auto">
        <table className="w-full max-w-[760px] min-w-[420px] text-start text-[13.5px]">
          <thead className="border-b border-trait text-[12.5px] text-encre-2">
            <tr><th className="py-1.5 pe-3 text-start font-semibold">{t('rec.critere')}</th>
              <th className="px-3 text-end font-semibold">{t('rec.avecOrigine')}</th><th className="ps-3 text-end font-semibold">{t('rec.avecRecal')}</th></tr>
          </thead>
          <tbody className="chiffres divide-y divide-trait-2">
            {lignes.map(([nom, f]) => (
              <tr key={nom}><td className="py-1.5 pe-3">{nom}</td><td className="px-3 text-end">{f(o)}</td>
                <td className="ps-3 text-end font-semibold">{v ? f(v) : '—'}</td></tr>
            ))}
            <tr><td className="py-1.5 pe-3">{t('rec.seuilMel', { R: r.rapport_cout })}</td>
              <td className="px-3 text-end">{nombre(r.seuil_mel.origine)}</td>
              <td className="ps-3 text-end font-semibold">{r.source_seuil === 'locale' ? nombre(r.seuil_mel.propose) : t('rec.inchange')}</td></tr>
          </tbody>
        </table>
      </div>
      <p className="text-[13px]">{t('rec.classes', { liste: recal.length ? liste(recal) : t('rec.aucuneClasse') })}</p>
      {r.recommandation && (() => {
        const ok = r.recommandation.decision === 'appliquer'
        const k = `rec.raison.${r.recommandation.raison}`
        return (
          <div className={`flex gap-2.5 rounded-[5px] px-3 py-2 text-[13.5px] ${ok ? 'bg-benin-pale text-benin' : 'bg-avis-pale text-avis'}`}>
            {ok ? <CircleCheck className="mt-0.5 size-4 shrink-0" aria-hidden /> : <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden />}
            <p><b>{ok ? t('rec.reco.appliquer') : t('rec.reco.conserver')}</b> {estCle(k) ? t(k) : ''}</p>
          </div>
        )
      })()}
      <p className="text-[12.5px] text-encre-2">{t('rec.noteEstimation')}</p>
    </div>
  )
}

function Recalibrage() {
  const [e, setE] = useState<EtatRecalibrage | null>(null)
  const [histo, setHisto] = useState(false)
  const [retour, setRetour] = useState<Retour>(null)
  const [enCours, setEnCours] = useState<string | null>(null)
  const [confirmer, setConfirmer] = useState<{ type: 'appliquer'; c: Calibration } | { type: 'revenir'; profil: Profil } | null>(null)
  const charger = () => api.recalibrage().then(setE).catch((x) => setRetour({ type: 'erreur', texte: x.message }))
  useEffect(() => { void charger() }, [])
  if (!e) return <Panneau titre={t('rec.titre')}><Chargement /></Panneau>
  const alpha = 0.1

  async function proposer(profil: Profil) {
    setEnCours(profil); setRetour(null)
    try { await api.proposerRecalibrage(profil, histo); await charger() }
    catch (x) { setRetour({ type: 'erreur', texte: (x as Error).message }) } finally { setEnCours(null) }
  }
  async function valider() {
    if (!confirmer) return
    setEnCours('confirmation')
    try {
      if (confirmer.type === 'appliquer') await api.appliquerRecalibrage(confirmer.c.id)
      else await api.reinitialiserRecalibrage(confirmer.profil)
      await charger(); setConfirmer(null)
    } catch (x) { setRetour({ type: 'erreur', texte: (x as Error).message }); setConfirmer(null) } finally { setEnCours(null) }
  }

  return (
    <div className="flex flex-col gap-6">
      <Panneau titre={t('rec.titre')}>
        <p className="max-w-prose text-[14px] text-encre-2">{t('rec.intro')}</p>
        <label className="mt-4 flex items-center gap-2.5 text-[14px]">
          <input type="checkbox" checked={histo} onChange={(x) => setHisto(x.target.checked)} className="size-4 accent-bloc" />
          {t('rec.histoSeulement')}
        </label>
        {retour && <div className="mt-3"><Message type={retour.type}>{retour.texte}</Message></div>}
      </Panneau>
      {(['complet', 'sans_contexte'] as Profil[]).map((profil) => {
        const p = e.profils[profil]
        const n = histo ? p.n_histologie : p.n_valides
        return (
          <Panneau key={profil} titre={t(`rec.profil.${profil}`)} actions={
            <Bouton variante="secondaire" chargement={enCours === profil} disabled={n < e.minimum_proposition} onClick={() => proposer(profil)}
              icone={<Scale className="size-4" aria-hidden />}>{t('rec.proposer')}</Bouton>}>
            <p className="text-[14px]">{t('rec.valides', { n: p.n_valides, h: p.n_histologie })}</p>
            <p className="mt-2 text-[13px] text-encre-2">{t('rec.parClasse', { min: e.minimum_par_classe })}</p>
            <ul className="mt-1.5 flex flex-wrap gap-1.5 text-[12.5px]">
              {CODES_CLASSES.map((k) => {
                const nk = p.par_classe[k] ?? 0
                return <li key={k} className={`rounded-[4px] px-2 py-0.5 ${nk >= e.minimum_par_classe ? 'bg-benin-pale text-benin' : 'bg-trait-2 text-encre-2'}`}>
                  {nomClasse(k)} : <b className="chiffres">{nk}</b></li>
              })}
            </ul>
            {n < e.minimum_proposition && <p className="mt-3 text-[13px] text-encre-2">{t('rec.minimum', { n: e.minimum_proposition })}</p>}
            <div className="mt-4 flex flex-wrap items-center gap-3 rounded-[5px] bg-porcelaine px-3 py-2 text-[14px]">
              <span className="font-semibold">{t('rec.seuilsActifs')}</span>
              <span>{p.active ? t('rec.locaux', { id: p.active.id, date: dateHeure(p.active.applique_le) }) : t('rec.origine')}</span>
              {p.active && <Bouton variante="discret" onClick={() => setConfirmer({ type: 'revenir', profil })}
                icone={<RotateCcw className="size-4" aria-hidden />}>{t('rec.revenir')}</Bouton>}
            </div>
            {p.propositions.map((c) => (
              <div key={c.id} className="mt-4 rounded-[5px] border border-trait-2 p-4">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <p className="font-semibold">{t('rec.proposition', { id: c.id, date: dateHeure(c.cree_le) })}
                    <span className="ms-2 text-[13px] font-normal text-encre-2">{t('rec.casUtilises', { n: c.resume.n })}</span></p>
                  {c.active ? <span className="rounded-[4px] bg-benin-pale px-2 py-0.5 text-[13px] font-semibold text-benin">{t('rec.active')}</span>
                    : <Bouton variante={c.resume.recommandation?.decision === 'conserver' ? 'secondaire' : 'principal'}
                        onClick={() => setConfirmer({ type: 'appliquer', c })}>{t('rec.appliquer')}</Bouton>}
                </div>
                <TableauProposition c={c} alpha={c.resume.alpha ?? alpha} />
              </div>
            ))}
          </Panneau>
        )
      })}
      <Confirmation ouvert={confirmer !== null} chargement={enCours === 'confirmation'} onFermer={() => setConfirmer(null)} onConfirmer={valider}
        titre={confirmer?.type === 'appliquer' ? t('rec.appliquer') : t('rec.revenir')}
        texte={confirmer?.type === 'appliquer' ? t('rec.confirmerAppliquer', { id: confirmer.c.id }) : t('rec.confirmerRevenir')}
        libelle={confirmer?.type === 'appliquer' ? t('rec.appliquer') : t('rec.revenir')} />
    </div>
  )
}

// ---- sauvegardes -------------------------------------------------------------------------------

function Sauvegardes() {
  const [listeS, setListe] = useState<Sauvegarde[] | null>(null)
  const [retour, setRetour] = useState<Retour>(null)
  const [enCours, setEnCours] = useState<string | null>(null)
  const [restaurer, setRestaurer] = useState<Sauvegarde | null>(null)
  const [supprimer, setSupprimer] = useState<Sauvegarde | null>(null)
  const entree = useRef<HTMLInputElement>(null)
  const charger = () => api.sauvegardes().then(setListe).catch((x) => setRetour({ type: 'erreur', texte: x.message }))
  useEffect(() => { void charger() }, [])

  async function agir(cle: string, f: () => Promise<string | void>) {
    setEnCours(cle); setRetour(null)
    try { const texte = await f(); if (texte) setRetour({ type: 'info', texte }); await charger() }
    catch (x) { setRetour({ type: 'erreur', texte: (x as Error).message }) } finally { setEnCours(null) }
  }
  const type = (s: Sauvegarde) => { const k = `sv.type.${s.type}`; return estCle(k) ? t(k) : s.type }
  const quand = (s: Sauvegarde) => (s.date ? dateHeure(s.date) : s.nom)

  async function confirmerRestauration() {
    if (!restaurer) return
    setEnCours('restauration')
    try {
      await api.restaurerSauvegarde(restaurer.nom)
      // Session fermée par le serveur et données remplacées : rechargement complet de l'interface.
      window.location.assign('/connexion?restauree=1')
    } catch (x) {
      setRetour({ type: 'erreur', texte: (x as Error).message }); setRestaurer(null); setEnCours(null)
    }
  }

  return (
    <Panneau titre={t('sv.titre')} actions={
      <div className="flex flex-wrap gap-2">
        <input ref={entree} type="file" accept=".zip,application/zip" className="hidden" onChange={(x) => {
          const f = x.target.files?.[0]; x.target.value = ''
          if (f) void agir('import', async () => t('sv.importee', { nom: (await api.importerSauvegarde(f)).nom }))
        }} />
        <Bouton variante="secondaire" chargement={enCours === 'import'} onClick={() => entree.current?.click()}
          icone={<Upload className="size-4" aria-hidden />}>{t('sv.importer')}</Bouton>
        <Bouton chargement={enCours === 'creation'} onClick={() => agir('creation', async () => t('sv.creee', { nom: (await api.creerSauvegarde()).nom }))}
          icone={<DatabaseBackup className="size-4" aria-hidden />}>{t('sv.maintenant')}</Bouton>
      </div>}>
      <p className="max-w-prose text-[14px] text-encre-2">{t('sv.intro')}</p>
      {retour && <div className="mt-3"><Message type={retour.type}>{retour.texte}</Message></div>}
      {!listeS ? <Chargement /> : listeS.length === 0 ? <p className="mt-4 text-[14px] text-encre-2">{t('sv.aucune')}</p> : (
        <ul className="-mx-5 mt-3 divide-y divide-trait-2">
          {listeS.map((s) => (
            <li key={s.nom} className="flex flex-wrap items-center justify-between gap-3 px-5 py-3">
              <div className="flex min-w-0 items-center gap-3">
                <Archive className="size-5 shrink-0 text-encre-3" aria-hidden />
                <div className="min-w-0">
                  <p className="font-semibold">{quand(s)} <span className="ms-1 rounded-[4px] bg-trait-2 px-1.5 py-0.5 text-[12px] font-semibold text-encre-2">{type(s)}</span></p>
                  <p className="text-[13px] text-encre-2">{t('sv.contenu', {
                    p: s.n_patients ?? '—', a: s.n_analyses ?? '—', i: s.n_images ?? '—', taille: t('commun.mo', { n: nombre(s.taille / 1e6, 1) }),
                  })}</p>
                </div>
              </div>
              {s.type !== 'illisible' && (
                <div className="flex flex-wrap gap-1">
                  {!DEMO && <a href={api.urlSauvegarde(s.nom)} download><Bouton variante="discret" icone={<Download className="size-4" aria-hidden />}>{t('sv.telecharger')}</Bouton></a>}
                  <Bouton variante="discret" onClick={() => setRestaurer(s)} icone={<RotateCcw className="size-4" aria-hidden />}>{t('sv.restaurer')}</Bouton>
                  <Bouton variante="discret" onClick={() => setSupprimer(s)} icone={<Trash2 className="size-4" aria-hidden />}>{t('sv.supprimer')}</Bouton>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      <Confirmation ouvert={restaurer !== null} danger chargement={enCours === 'restauration'} onFermer={() => setRestaurer(null)}
        onConfirmer={confirmerRestauration} titre={restaurer ? t('sv.confirmerRestaurer', { date: quand(restaurer) }) : ''}
        texte={t('sv.restaurerTexte')} libelle={enCours === 'restauration' ? t('sv.enCours') : t('sv.restaurer')} />
      <Confirmation ouvert={supprimer !== null} danger onFermer={() => setSupprimer(null)}
        onConfirmer={() => { const s = supprimer!; setSupprimer(null); void agir('suppression', async () => { await api.supprimerSauvegarde(s.nom) }) }}
        titre={t('sv.supprimer')} texte={supprimer ? t('sv.confirmerSuppr', { nom: supprimer.nom }) : ''} libelle={t('sv.supprimer')} />
    </Panneau>
  )
}

const ONGLETS: { id: string; libelle: () => string; contenu: () => ReactNode }[] = [
  { id: 'comptes', libelle: () => t('adm.ongletComptes'), contenu: () => <div className="grid items-start gap-6 xl:grid-cols-2"><Comptes /><Reglages /></div> },
  { id: 'recalibrage', libelle: () => t('adm.ongletRecal'), contenu: () => <Recalibrage /> },
  { id: 'sauvegardes', libelle: () => t('adm.ongletSauv'), contenu: () => <Sauvegardes /> },
  { id: 'journal', libelle: () => t('adm.ongletJournal'), contenu: () => <Journal /> },
]

export function Administration() {
  const [params, setParams] = useSearchParams()
  const actif = ONGLETS.find((o) => o.id === params.get('onglet')) ?? ONGLETS[0]
  return (
    <>
      <EnTete titre={t('nav.administration')} sousTitre={t('adm.sousTitre')} />
      <div role="tablist" aria-label={t('nav.administration')} className="mb-6 flex gap-1 overflow-x-auto border-b border-trait">
        {ONGLETS.map((o) => (
          <button key={o.id} role="tab" aria-selected={o.id === actif.id} onClick={() => setParams({ onglet: o.id }, { replace: true })}
            className={`-mb-px border-b-2 px-3.5 py-2 text-[14.5px] font-semibold whitespace-nowrap ${o.id === actif.id
              ? 'border-bloc text-bloc-fonce' : 'border-transparent text-encre-2 hover:text-encre'}`}>
            {o.libelle()}
          </button>
        ))}
      </div>
      <div role="tabpanel">{actif.contenu()}</div>
    </>
  )
}

export function Compte() {
  const { utilisateur } = useApp()
  const [f, setF] = useState({ ancien: '', nouveau: '', confirmation: '' })
  const [message, setMessage] = useState<Retour>(null)
  async function envoyer(e: FormEvent) {
    e.preventDefault()
    if (f.nouveau !== f.confirmation) { setMessage({ type: 'erreur', texte: t('cpt.differents') }); return }
    try { await api.changerMotDePasse(f.ancien, f.nouveau); setF({ ancien: '', nouveau: '', confirmation: '' }); setMessage({ type: 'info', texte: t('cpt.modifie') }) }
    catch (err) { setMessage({ type: 'erreur', texte: (err as Error).message }) }
  }
  return (
    <>
      <EnTete titre={t('nav.monCompte')} sousTitre={t('cpt.sousTitre', { nom: utilisateur?.nom_complet ?? '', id: utilisateur?.identifiant ?? '' })} />
      <Panneau titre={t('cpt.changer')} className="max-w-lg">
        <form onSubmit={envoyer} className="flex flex-col gap-4">
          {message && <Message type={message.type}>{message.texte}</Message>}
          <Champ label={t('cpt.actuel')}>{(id) => <Saisie id={id} type="password" autoComplete="current-password" value={f.ancien} onChange={(e) => setF({ ...f, ancien: e.target.value })} required />}</Champ>
          <Champ label={t('cpt.nouveau')} aide={t('acces.mdpAide')}>{(id) => <Saisie id={id} type="password" autoComplete="new-password" value={f.nouveau} onChange={(e) => setF({ ...f, nouveau: e.target.value })} required minLength={10} />}</Champ>
          <Champ label={t('cpt.confirmer')}>{(id) => <Saisie id={id} type="password" autoComplete="new-password" value={f.confirmation} onChange={(e) => setF({ ...f, confirmation: e.target.value })} required />}</Champ>
          <Bouton type="submit" className="self-start">{t('cpt.changer')}</Bouton>
        </form>
      </Panneau>
    </>
  )
}
