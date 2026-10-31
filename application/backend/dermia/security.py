"""Authentification et protections de base.

- Mots de passe : scrypt (bibliothèque standard), sel aléatoire, comparaison à temps constant.
- Session : jeton JWT signé dans un cookie HttpOnly, SameSite=Strict (inaccessible au JavaScript).
- Requêtes modifiantes : l'en-tête Origin, s'il est présent, doit être celui de l'application (anti-CSRF).
- Connexion : 5 échecs en 15 minutes bloquent l'identifiant temporairement.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from . import config
from .db import Utilisateur, get_db

COOKIE = "dermia_session"
_CLE = config.secret_key()
_N, _R, _P = 2 ** 14, 8, 1


def hacher(mot_de_passe: str) -> str:
    sel = secrets.token_bytes(16)
    h = hashlib.scrypt(mot_de_passe.encode(), salt=sel, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${base64.b64encode(sel).decode()}${base64.b64encode(h).decode()}"


def verifier(mot_de_passe: str, stocke: str) -> bool:
    try:
        _, n, sel, h = stocke.split("$")
        calc = hashlib.scrypt(mot_de_passe.encode(), salt=base64.b64decode(sel), n=int(n), r=_R, p=_P, dklen=32)
        return hmac.compare_digest(calc, base64.b64decode(h))
    except (ValueError, TypeError):
        return False


def valider_mot_de_passe(mdp: str) -> None:
    if len(mdp) < 10 or mdp.isdigit() or mdp.isalpha():
        raise HTTPException(422, "Le mot de passe doit contenir au moins 10 caractères, avec des lettres et des chiffres.")


def creer_jeton(u: Utilisateur) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=config.DUREE_SESSION_H)
    return jwt.encode({"sub": str(u.id), "role": u.role, "exp": exp}, _CLE, algorithm="HS256")


def poser_cookie(response, jeton: str) -> None:
    response.set_cookie(COOKIE, jeton, httponly=True, samesite="strict", secure=False,
                        max_age=config.DUREE_SESSION_H * 3600, path="/")


# ---- limitation des tentatives de connexion ---------------------------------------------
_ECHECS: dict[str, deque] = defaultdict(deque)
FENETRE_S, MAX_ECHECS = 15 * 60, 5


def verifier_tentatives(identifiant: str) -> None:
    q = _ECHECS[identifiant.lower()]
    while q and q[0] < time.time() - FENETRE_S:
        q.popleft()
    if len(q) >= MAX_ECHECS:
        raise HTTPException(429, "Trop de tentatives. Réessayez dans quelques minutes.")


def noter_echec(identifiant: str) -> None:
    _ECHECS[identifiant.lower()].append(time.time())


def effacer_echecs(identifiant: str) -> None:
    _ECHECS.pop(identifiant.lower(), None)


# ---- dépendances FastAPI ------------------------------------------------------------------
def utilisateur_courant(request: Request, db: Session = Depends(get_db)) -> Utilisateur:
    jeton = request.cookies.get(COOKIE)
    if not jeton:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session absente.")
    try:
        data = jwt.decode(jeton, _CLE, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expirée.")
    u = db.get(Utilisateur, int(data["sub"]))
    if u is None or not u.actif:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Compte désactivé.")
    return u


def admin_requis(u: Utilisateur = Depends(utilisateur_courant)) -> Utilisateur:
    if u.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé aux administrateurs.")
    return u


async def controle_origine(request: Request, call_next):
    """Refuse les requêtes modifiantes venant d'une autre origine (protection CSRF)."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origine = request.headers.get("origin")
        autorisees = {str(request.base_url).rstrip("/")} | config.ORIGINES_AUTORISEES
        if origine and origine.rstrip("/") not in autorisees:
            from fastapi.responses import JSONResponse

            from .i18n import langue, traduire
            return JSONResponse({"detail": traduire("Origine refusée.", langue(request))}, status_code=403)
    return await call_next(request)
