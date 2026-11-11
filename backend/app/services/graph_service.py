"""Load a repo's stored graphs into NetworkX and answer structural questions."""
import networkx as nx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Edge, File, Symbol


async def load_graphs(session: AsyncSession, repo_id: int) -> tuple[nx.DiGraph, nx.DiGraph]:
    fg, sg = nx.DiGraph(), nx.DiGraph()
    fg.add_nodes_from((await session.execute(select(File.path).where(File.repo_id == repo_id))).scalars())
    for s in (await session.execute(select(Symbol).where(Symbol.repo_id == repo_id))).scalars():
        sg.add_node(s.uid, path=s.file_path, name=s.name, qualname=s.qualname, kind=s.kind,
                    start_line=s.start_line, end_line=s.end_line)
    for e in (await session.execute(select(Edge).where(Edge.repo_id == repo_id))).scalars():
        (fg if e.kind == "imports" else sg).add_edge(e.src, e.dst)
    return fg, sg


async def find_symbols(session: AsyncSession, repo_id: int, q: str, limit: int = 20) -> list[Symbol]:
    like = f"%{q}%"
    stmt = (select(Symbol).where(Symbol.repo_id == repo_id,
                                 or_(Symbol.uid == q, Symbol.name.ilike(like), Symbol.qualname.ilike(like)))
            .order_by((Symbol.uid == q).desc(), (Symbol.name == q).desc(), Symbol.qualname).limit(limit))
    return list((await session.execute(stmt)).scalars())


async def resolve_symbol(session: AsyncSession, repo_id: int, q: str) -> tuple[Symbol | None, list[Symbol]]:
    """Resolve a uid or a name to ONE symbol. Returns (symbol, candidates); symbol is None when the query is
    unknown (no candidates) or ambiguous (several candidates). Same rules the /impact endpoint has always used."""
    matches = await find_symbols(session, repo_id, q, limit=10)
    exact = ([m for m in matches if m.uid == q] or ([matches[0]] if len(matches) == 1 else [m for m in matches if m.name == q])
             or [m for m in matches if m.qualname == q])         # "Class.method" is exact when it names one symbol
    return (exact[0] if len(exact) == 1 else None), matches
