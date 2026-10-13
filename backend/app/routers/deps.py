from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Repository


def get_repo(repo_id: int, db: Session = Depends(get_db)) -> Repository:
    repo = db.get(Repository, repo_id)
    if repo is None:
        raise HTTPException(404, f"Repository {repo_id} not found")
    return repo


def get_ready_repo(repo: Repository = Depends(get_repo)) -> Repository:
    if repo.status != "ready":
        raise HTTPException(409, f"Repository is '{repo.status}', not ready yet"
                                 + (f": {repo.error}" if repo.error else ""))
    return repo
