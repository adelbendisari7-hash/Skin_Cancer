"""Application FastAPI : API REST sous /api et interface web servie à la racine."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__, config, sauvegarde, service
from .i18n import langue, traduire, traduire_detail
from .api import analyses, comptes, lesions, patients, recalibrage, sauvegardes, systeme
from .db import init_db
from .security import controle_origine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s : %(message)s")


@asynccontextmanager
async def cycle_de_vie(_: FastAPI):
    init_db()
    config.IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    service.charger()
    if config.SAUVEGARDE_AUTO:
        service.sauvegardes_automatiques()
    yield


def creer_app() -> FastAPI:
    app = FastAPI(title=f"{config.NOM_PRODUIT} — API", version=__version__, lifespan=cycle_de_vie,
                  docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")
    app.middleware("http")(controle_origine)

    @app.middleware("http")
    async def maintenance(request: Request, call_next):
        if sauvegarde.MAINTENANCE.is_set() and request.url.path.startswith("/api/"):
            return JSONResponse({"detail": traduire("Restauration en cours. Réessayez dans un instant.", langue(request))},
                                status_code=503)
        return await call_next(request)

    @app.middleware("http")
    async def entetes_securite(request: Request, call_next):
        r = await call_next(request)
        r.headers.setdefault("X-Content-Type-Options", "nosniff")
        r.headers.setdefault("X-Frame-Options", "DENY")
        r.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.url.path.startswith("/api/") and "Cache-Control" not in r.headers:
            r.headers["Cache-Control"] = "no-store"
        return r

    for module in (systeme, comptes, patients, analyses, lesions, recalibrage, sauvegardes):
        app.include_router(module.router)

    @app.exception_handler(StarletteHTTPException)
    async def erreur_http(request: Request, exc: StarletteHTTPException):
        return JSONResponse({"detail": traduire_detail(exc.detail, langue(request))}, status_code=exc.status_code,
                            headers=getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def erreur_interne(request: Request, exc: Exception):
        logging.getLogger("dermia").exception("Erreur non gérée")
        return JSONResponse({"detail": traduire("Erreur interne du serveur. Consultez le journal technique.",
                                                langue(request))}, status_code=500)

    # ---- interface web (fichiers construits par `npm run build`) ------------------------------
    dist = config.FRONTEND_DIR
    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{chemin:path}", include_in_schema=False)
    def interface(chemin: str, request: Request):
        if chemin.startswith("api/"):
            return JSONResponse({"detail": traduire("Ressource introuvable.", langue(request))}, status_code=404)
        fichier = dist / chemin
        if chemin and fichier.is_file() and dist in fichier.resolve().parents:
            return FileResponse(fichier)
        index = dist / "index.html"
        if index.exists():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return JSONResponse({"detail": "Interface non construite : lancez `npm run build` dans application/frontend."},
                            status_code=503)

    return app


app = creer_app()
