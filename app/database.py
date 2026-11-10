from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

DATABASE_URL = "sqlite:///./swarm_vault.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class AgentAccount(Base):
    __tablename__ = "agent_accounts"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    platform = Column(String, index=True)  # "x" or "facebook"
    persona = Column(Text)
    proxy_url = Column(String, nullable=True)
    cookies_json = Column(Text, nullable=True)  # Raw JSON cookies string
    status = Column(String, default="ready")    # "ready", "quarantined", "mock"
    created_at = Column(DateTime, default=datetime.utcnow)

class CampaignLog(Base):
    __tablename__ = "campaign_logs"

    id = Column(Integer, primary_key=True, index=True)
    target_url = Column(String)
    agent_username = Column(String)
    platform = Column(String)
    generated_comment = Column(Text)
    action_status = Column(String)  # "completed", "simulated", "failed"
    screenshot_path = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

def init_db():
    Base.metadata.create_all(bind=engine)