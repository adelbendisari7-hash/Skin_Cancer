import { CircleAlert, Info, LoaderCircle, X } from 'lucide-react'
import {
  useEffect, useId, useRef,
  type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type Ref, type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react'
import { t } from '../i18n'

type Variante = 'principal' | 'secondaire' | 'discret' | 'danger'

const VARIANTES: Record<Variante, string> = {
  principal: 'bg-bloc text-white hover:bg-bloc-fonce disabled:bg-encre-3',
  secondaire: 'bg-surface text-encre border border-trait hover:border-encre-3 disabled:text-encre-3',
  discret: 'text-bloc hover:bg-bloc-pale disabled:text-encre-3',
  danger: 'bg-surface text-urgent border border-urgent/40 hover:bg-urgent-pale',
}

export function Bouton({ variante = 'principal', chargement = false, icone, children, className = '', ref, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variante?: Variante; chargement?: boolean; icone?: ReactNode; ref?: Ref<HTMLButtonElement> }) {
  return (
    <button
      ref={ref}
      {...rest}
      disabled={rest.disabled || chargement}
      className={`inline-flex items-center justify-center gap-2 rounded-[5px] px-4 py-2 text-[14px] font-semibold
        transition-colors disabled:cursor-not-allowed ${VARIANTES[variante]} ${className}`}
    >
      {chargement ? <LoaderCircle className="size-4 animate-spin" aria-hidden /> : icone}
      {children}
    </button>
  )
}

export function Champ({ label, aide, erreur, children }: { label: string; aide?: ReactNode; erreur?: string | null; children: (id: string) => ReactNode }) {
  const id = useId()
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-[14px] font-semibold text-encre">{label}</label>
      {children(id)}
      {aide && !erreur && <p className="text-[13px] text-encre-2">{aide}</p>}
      {erreur && <p className="text-[13px] text-urgent">{erreur}</p>}
    </div>
  )
}

const CHAMP = `w-full rounded-[5px] border border-trait bg-surface px-3 py-2 text-[15px] text-encre
  placeholder:text-encre-3 hover:border-encre-3 focus:border-bloc focus:outline-none focus:ring-2 focus:ring-bloc/25`

export const Saisie = (p: InputHTMLAttributes<HTMLInputElement>) => <input {...p} className={`${CHAMP} ${p.className ?? ''}`} />
export const Liste = (p: SelectHTMLAttributes<HTMLSelectElement>) => <select {...p} className={`${CHAMP} ${p.className ?? ''}`} />
export const Texte = (p: TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...p} className={`${CHAMP} ${p.className ?? ''}`} />

export function Message({ type = 'erreur', children }: { type?: 'erreur' | 'info'; children: ReactNode }) {
  const erreur = type === 'erreur'
  return (
    <div role={erreur ? 'alert' : 'status'}
      className={`flex gap-2.5 rounded-[5px] border px-3 py-3 text-[14px] ${erreur
        ? 'border-urgent/30 bg-urgent-pale text-urgent' : 'border-renvoi/20 bg-renvoi-pale text-renvoi'}`}>
      {erreur ? <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden /> : <Info className="mt-0.5 size-4 shrink-0" aria-hidden />}
      <div>{children}</div>
    </div>
  )
}

export function Chargement({ texte }: { texte?: string }) {
  return (
    <div className="flex items-center gap-2 py-10 text-encre-2" role="status">
      <LoaderCircle className="size-5 animate-spin" aria-hidden /> {texte ?? t('commun.chargement')}
    </div>
  )
}

export function EnTete({ titre, sousTitre, actions }: { titre: ReactNode; sousTitre?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-7 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-[26px] font-semibold leading-tight">{titre}</h1>
        {sousTitre && <div className="mt-1 text-[15px] text-encre-2">{sousTitre}</div>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  )
}

export function Panneau({ titre, actions, children, className = '' }: { titre?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-lg border border-trait bg-surface ${className}`}>
      {titre && (
        <div className="flex items-center justify-between gap-3 border-b border-trait-2 px-5 py-3">
          <h2 className="text-[16px] font-semibold">{titre}</h2>
          {actions}
        </div>
      )}
      <div className="px-5 py-4">{children}</div>
    </section>
  )
}

export function Vide({ titre, texte, action }: { titre: string; texte?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-2 py-8">
      <p className="text-[16px] font-semibold">{titre}</p>
      {texte && <p className="max-w-prose text-[14px] text-encre-2">{texte}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}

export function Dialogue({ ouvert, titre, onFermer, children }: { ouvert: boolean; titre: string; onFermer: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (ouvert && !d.open) d.showModal()           // <dialog> natif : focus piégé et touche Échap
    if (!ouvert && d.open) d.close()
  }, [ouvert])
  return (
    <dialog ref={ref} onClose={onFermer} aria-labelledby="titre-dialogue"
      className="m-auto w-[min(560px,calc(100vw-32px))] rounded-lg border border-trait bg-surface p-0 text-encre
        backdrop:bg-encre/40">
      <div className="flex items-center justify-between border-b border-trait-2 px-5 py-3">
        <h2 id="titre-dialogue" className="text-[17px] font-semibold">{titre}</h2>
        <button onClick={onFermer} className="rounded p-1 text-encre-2 hover:bg-trait-2" aria-label={t('commun.fermer')}>
          <X className="size-5" aria-hidden />
        </button>
      </div>
      <div className="px-5 py-4">{ouvert && children}</div>
    </dialog>
  )
}

/** Demande de confirmation dans l'application (visible, traduite, accessible au clavier). */
export function Confirmation({ ouvert, titre, texte, libelle, danger = false, chargement = false, onConfirmer, onFermer }: {
  ouvert: boolean; titre: string; texte: ReactNode; libelle: string; danger?: boolean; chargement?: boolean
  onConfirmer: () => void; onFermer: () => void
}) {
  return (
    <Dialogue ouvert={ouvert} titre={titre} onFermer={onFermer}>
      <div className="text-[14px]">{texte}</div>
      <div className="mt-5 flex flex-wrap gap-2">
        <Bouton variante={danger ? 'danger' : 'principal'} chargement={chargement} onClick={onConfirmer}>{libelle}</Bouton>
        <Bouton variante="secondaire" onClick={onFermer}>{t('commun.annuler')}</Bouton>
      </div>
    </Dialogue>
  )
}
