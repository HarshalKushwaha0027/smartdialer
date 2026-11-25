"""
Borrower Queue.

Same atomicity pattern as agent_manager: reservation is a single
conditional UPDATE (`WHERE reserved = false AND already_called = false`)
so two workers can never both grab the same borrower.
"""
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..models import Borrower


def try_reserve_borrower(db: Session, borrower_id: str) -> bool:
    result = db.execute(
        update(Borrower)
        .where(Borrower.id == borrower_id, Borrower.reserved == False, Borrower.already_called == False)  # noqa: E712
        .values(reserved=True)
    )
    db.commit()
    return result.rowcount == 1


def try_reserve_next_borrower(db: Session) -> Borrower | None:
    candidates = (
        db.query(Borrower.id)
        .filter(Borrower.reserved == False, Borrower.already_called == False)  # noqa: E712
        .order_by(Borrower.updated_at.asc())
        .limit(25)
        .all()
    )
    for (borrower_id,) in candidates:
        if try_reserve_borrower(db, borrower_id):
            return db.get(Borrower, borrower_id)
    return None


def release_borrower(db: Session, borrower_id: str, *, called: bool) -> None:
    """
    Release a reserved borrower. If `called` is True the borrower is
    marked already_called so they are never dialed again, even if the
    call ultimately failed to connect (one attempt is one attempt).
    """
    borrower = db.get(Borrower, borrower_id)
    if borrower is None:
        return
    borrower.reserved = False
    if called:
        borrower.already_called = True
    db.commit()


def remaining_count(db: Session) -> int:
    return db.query(Borrower).filter(Borrower.already_called == False).count()  # noqa: E712
