from fastapi import APIRouter, HTTPException
from sqlalchemy import select, func
from typing import List

from app.deps import CurrentUser, DbSession
from app.models.account import AlpacaAccount, AccountMode
from app.models.bucket import Bucket
from app.schemas.account import AccountCreate, AccountOut, AccountTestResult
from app.security import encrypt_secret
from app.services.alpaca import get_base_url

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _get_account_or_404(db, user_id: int, account_id: int) -> AlpacaAccount:
    acct = db.execute(
        select(AlpacaAccount).where(
            AlpacaAccount.id == account_id,
            AlpacaAccount.user_id == user_id,
        )
    ).scalar_one_or_none()
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")
    return acct


@router.get("", response_model=List[AccountOut])
def list_accounts(current_user: CurrentUser, db: DbSession):
    accounts = db.execute(
        select(AlpacaAccount).where(AlpacaAccount.user_id == current_user.id)
    ).scalars().all()
    return accounts


@router.post("", response_model=AccountOut, status_code=201)
def create_account(body: AccountCreate, current_user: CurrentUser, db: DbSession):
    base_url = get_base_url(body.mode)
    acct = AlpacaAccount(
        user_id=current_user.id,
        label=body.label,
        mode=body.mode,
        api_key=body.api_key,
        api_secret_enc=encrypt_secret(body.api_secret),
        base_url=base_url,
    )
    db.add(acct)
    db.commit()
    db.refresh(acct)
    return acct


@router.delete("/{account_id}")
def delete_account(account_id: int, current_user: CurrentUser, db: DbSession):
    acct = _get_account_or_404(db, current_user.id, account_id)
    unlinked_count = db.execute(
        select(func.count()).select_from(Bucket).where(
            Bucket.account_id == account_id,
        )
    ).scalar() or 0
    db.delete(acct)
    db.commit()
    return {
        "status": "deleted",
        "unlinked_bucket_count": unlinked_count,
    }


@router.post("/{account_id}/test", response_model=AccountTestResult)
def test_account(account_id: int, current_user: CurrentUser, db: DbSession):
    acct = _get_account_or_404(db, current_user.id, account_id)
    try:
        from app.services.alpaca import get_trading_client
        client = get_trading_client(acct)
        alpaca_acct = client.get_account()
        return AccountTestResult(
            ok=True,
            message="Connection successful",
            account_id=str(alpaca_acct.id),
            buying_power=float(alpaca_acct.buying_power) if alpaca_acct.buying_power else None,
        )
    except Exception as exc:
        return AccountTestResult(ok=False, message=str(exc))


@router.post("/{account_id}/sync", status_code=202)
def sync_account_now(account_id: int, current_user: CurrentUser, db: DbSession):
    acct = _get_account_or_404(db, current_user.id, account_id)
    from app.services.sync import sync_account
    sync_account(db, acct)
    return {"status": "synced"}
