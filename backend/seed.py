#!/usr/bin/env python3
"""Seed demo user: demo@example.com / demo12345."""
import sys
import os

# Ensure app is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select
from app.db import SessionLocal
from app.models.user import User
from app.security import hash_password


def seed() -> None:
    db = SessionLocal()
    try:
        existing = db.execute(select(User).where(User.email == "demo@example.com")).scalar_one_or_none()
        if existing:
            print("Demo user already exists, skipping.")
            return

        demo = User(
            email="demo@example.com",
            password_hash=hash_password("demo12345"),
        )
        db.add(demo)
        db.commit()
        print("Created demo user: demo@example.com / demo12345")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
