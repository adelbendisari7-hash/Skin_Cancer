import { createContext, Fragment, useContext, useState, type ReactNode } from 'react'
import { definirLangue, LANGUES, langueCourante, t, type Langue } from '../i18n'

const Ctx = createContext<{ langue: Langue; changer: (l: Langue) => void } | null>(null)

export function FournisseurLangue({ children }: { children: ReactNode }) {
  const [langue, setLangue] = useState<Langue>(langueCourante())
  function changer(l: Langue) {
    definirLangue(l)
    setLangue(l)
  }
  // La clé remonte l'application : tous les textes, dates et nombres sont recalculés dans la nouvelle langue.
  return <Ctx.Provider value={{ langue, changer }}><Fragment key={langue}>{children}</Fragment></Ctx.Provider>
}

/** Sélecteur de langue compact (barre latérale, écrans d'accès). */
export function ChoixLangue({ className = '' }: { className?: string }) {
  const c = useContext(Ctx)
  if (!c) return null
  return (
    <div role="group" aria-label={t('commun.langue')} className={`inline-flex rounded-[5px] border border-trait bg-surface p-0.5 text-[13px] ${className}`}>
      {LANGUES.map((l) => (
        <button key={l.code} type="button" lang={l.code} onClick={() => c.changer(l.code)} aria-pressed={c.langue === l.code}
          className={`rounded-[4px] px-2.5 py-1 font-semibold ${c.langue === l.code ? 'bg-bloc text-white' : 'text-encre-2 hover:text-encre'}`}>
          {l.nom}
        </button>
      ))}
    </div>
  )
}
