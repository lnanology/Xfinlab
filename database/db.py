from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    ForeignKey,
    JSON,
    TIMESTAMP,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# PostgreSQL 連接 URL
DATABASE_URL = "sqlite:///./xfinlab.db"
# 初始化 SQLAlchemy Engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

# 建立 Session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 基類
Base = declarative_base()


# Users Table
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), default="user")
    created_at = Column(TIMESTAMP, default=datetime.utcnow)


# Research Records Table
class ResearchRecord(Base):
    __tablename__ = "research_records"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    symbol = Column(String(50), nullable=False)
    research_type = Column(String(100), nullable=False)
    result = Column(JSON)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)


# Analysis Records Table
class AnalysisRecord(Base):
    __tablename__ = "analysis_records"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    symbol = Column(String(50), nullable=False)
    analysis_type = Column(String(100), nullable=False)
    score = Column(Integer)
    result = Column(JSON)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)


# Watchlists Table
class Watchlist(Base):
    __tablename__ = "watchlists"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    symbol = Column(String(50), nullable=False)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)


# Events Table
class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(50), nullable=False)
    event_type = Column(String(100), nullable=False)
    event_score = Column(Integer)
    risk_score = Column(Integer)
    description = Column(Text)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)


# Strategies Table
class Strategy(Base):
    __tablename__ = "strategies"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    version = Column(String(50))
    config_json = Column(JSON)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)


# Decision Journal Table
class DecisionJournal(Base):
    __tablename__ = "decision_journal"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    symbol = Column(String(50), nullable=False)
    decision = Column(String(100), nullable=False)
    reason = Column(Text)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)


# Audit Logs Table
class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    action = Column(String(100), nullable=False)
    ip_address = Column(String(50))
    created_at = Column(TIMESTAMP, default=datetime.utcnow)


# 創建所有表
Base.metadata.create_all(bind=engine)


# 獲取數據庫 Session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
