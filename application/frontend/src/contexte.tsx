import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, ErreurApi, type Etat, type Utilisateur } from './api'

interface ContexteApp {
  etat: Etat | null
  utilisateur: Utilisateur | null
  chargement: boolean
  erreur: string | null
  rafraichir: () => Promise<void>
  definirUtilisateur: (u: Utilisateur | null) => void
  deconnecter: () => Promise<void>
}

const Ctx = createContext<ContexteApp | null>(null)

export function FournisseurApp({ children }: { children: ReactNode }) {
  const [etat, setEtat] = useState<Etat | null>(null)
  const [utilisateur, setUtilisateur] = useState<Utilisateur | null>(null)
  const [chargement, setChargement] = useState(true)
  const [erreur, setErreur] = useState<string | null>(null)

  const rafraichir = useCallback(async () => {
    try {
      const e = await api.etat()
      setEtat(e)
      document.title = e.produit
      if (!e.installation_requise) {
        try {
          setUtilisateur(await api.moi())
        } catch (err) {
          if (!(err instanceof ErreurApi && err.statut === 401)) throw err
          setUtilisateur(null)
        }
      }
      setErreur(null)
    } catch (err) {
      setErreur(err instanceof Error ? err.message : String(err))
    } finally {
      setChargement(false)
    }
  }, [])

  useEffect(() => { void rafraichir() }, [rafraichir])

  const deconnecter = useCallback(async () => {
    await api.deconnexion().catch(() => undefined)
    setUtilisateur(null)
  }, [])

  return (
    <Ctx.Provider value={{ etat, utilisateur, chargement, erreur, rafraichir, definirUtilisateur: setUtilisateur, deconnecter }}>
      {children}
    </Ctx.Provider>
  )
}

export function useApp(): ContexteApp {
  const c = useContext(Ctx)
  if (!c) throw new Error('useApp hors du FournisseurApp')
  return c
}
