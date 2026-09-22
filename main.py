from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "henn.db"

app = FastAPI(
    title="HentaiLa API",
    description="API con datos scrapeados de HentaiLa (animes, episodios y players).",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ============ MODELOS ============
class Episodio(BaseModel):
    num: int
    url: str
    players: List[str]

class AnimeResumen(BaseModel):
    slug: str
    titulo: str
    tipo: Optional[str]
    año: Optional[int]
    generos: List[str]
    portada: Optional[str] = None

class AnimeDetalle(BaseModel):
    slug: str
    titulo: str
    tipo: Optional[str]
    año: Optional[int]
    generos: List[str]
    sinopsis: Optional[str]
    portada: Optional[str] = None
    url: str
    episodios: List[Episodio]

# ============ HELPERS ============
def tiene_columna(row, nombre):
    """Comprueba si el row de sqlite3 tiene una columna concreta."""
    return nombre in row.keys()

def row_a_anime_resumen(row):
    return {
        "slug": row["slug"],
        "titulo": row["titulo"],
        "tipo": row["tipo"],
        "año": row["año"],
        "generos": [g.strip() for g in (row["generos"] or "").split(",") if g.strip()],
        "portada": row["portada"] if tiene_columna(row, "portada") else None,
    }

def row_a_episodio(row):
    return {
        "num": row["num"],
        "url": row["url"],
        "players": [p.strip() for p in (row["players"] or "").split(",") if p.strip()],
    }

# ============ ENDPOINTS ============
@app.get("/")
def root():
    return {
        "api": "HentaiLa API",
        "version": "1.0.0",
        "endpoints": {
            "/animes": "Lista animes (filtrable)",
            "/animes/{slug}": "Detalle de un anime",
            "/animes/{slug}/episodios": "Episodios de un anime",
            "/generos": "Lista de géneros",
            "/stats": "Estadísticas generales"
        }
    }

@app.get("/stats")
def stats():
    conn = get_db()
    cur = conn.cursor()
    total_animes = cur.execute("SELECT COUNT(*) FROM animes").fetchone()[0]
    total_eps = cur.execute("SELECT COUNT(*) FROM episodios").fetchone()[0]
    clasicos = cur.execute("SELECT COUNT(*) FROM animes WHERE año <= 2008").fetchone()[0]
    conn.close()
    return {
        "total_animes": total_animes,
        "total_episodios": total_eps,
        "clasicos_2008": clasicos
    }

@app.get("/generos")
def generos():
    conn = get_db()
    cur = conn.cursor()
    rows = cur.execute("SELECT generos FROM animes WHERE generos != ''").fetchall()
    conn.close()
    set_gen = set()
    for r in rows:
        for g in (r[0] or "").split(","):
            g = g.strip()
            if g:
                set_gen.add(g)
    return {"total": len(set_gen), "generos": sorted(set_gen)}

@app.get("/animes")
def listar_animes(
    max_year: Optional[int] = Query(None, description="Año máximo (ej: 2008 para clásicos)"),
    min_year: Optional[int] = Query(None, description="Año mínimo"),
    genero: Optional[str] = Query(None, description="Filtrar por género"),
    tipo: Optional[str] = Query(None, description="OVA, TV, Movie..."),
    q: Optional[str] = Query(None, description="Búsqueda por título"),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100)
):
    conn = get_db()
    cur = conn.cursor()
    
    where = []
    params = []
    
    if max_year is not None:
        where.append("año <= ?")
        params.append(max_year)
    if min_year is not None:
        where.append("año >= ?")
        params.append(min_year)
    if genero:
        where.append("generos LIKE ?")
        params.append(f"%{genero}%")
    if tipo:
        where.append("tipo = ?")
        params.append(tipo)
    if q:
        where.append("titulo LIKE ?")
        params.append(f"%{q}%")
    
    where_sql = "WHERE " + " AND ".join(where) if where else ""
    offset = (page - 1) * limit
    
    total = cur.execute(f"SELECT COUNT(*) FROM animes {where_sql}", params).fetchone()[0]
    rows = cur.execute(
        f"SELECT * FROM animes {where_sql} ORDER BY año DESC, titulo LIMIT ? OFFSET ?",
        params + [limit, offset]
    ).fetchall()
    conn.close()
    
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "paginas_totales": (total + limit - 1) // limit,
        "animes": [row_a_anime_resumen(r) for r in rows]
    }

@app.get("/animes/{slug}")
def obtener_anime(slug: str):
    conn = get_db()
    cur = conn.cursor()
    anime = cur.execute("SELECT * FROM animes WHERE slug = ?", (slug,)).fetchone()
    if not anime:
        conn.close()
        raise HTTPException(404, "Anime no encontrado")
    
    eps = cur.execute(
        "SELECT * FROM episodios WHERE slug = ? ORDER BY num",
        (slug,)
    ).fetchall()
    conn.close()
    
    return {
        "slug": anime["slug"],
        "titulo": anime["titulo"],
        "tipo": anime["tipo"],
        "año": anime["año"],
        "generos": [g.strip() for g in (anime["generos"] or "").split(",") if g.strip()],
        "sinopsis": anime["sinopsis"],
        "portada": anime["portada"] if tiene_columna(anime, "portada") else None,
        "url": anime["url"],
        "episodios": [row_a_episodio(e) for e in eps]
    }

@app.get("/animes/{slug}/episodios")
def obtener_episodios(slug: str):
    conn = get_db()
    cur = conn.cursor()
    existe = cur.execute("SELECT 1 FROM animes WHERE slug = ?", (slug,)).fetchone()
    if not existe:
        conn.close()
        raise HTTPException(404, "Anime no encontrado")
    eps = cur.execute(
        "SELECT * FROM episodios WHERE slug = ? ORDER BY num",
        (slug,)
    ).fetchall()
    conn.close()
    return {"slug": slug, "total": len(eps), "episodios": [row_a_episodio(e) for e in eps]}
