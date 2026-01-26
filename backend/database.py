from sqlalchemy import create_engine, Column, Integer, String, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "sqlite:///./pico_resq.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class Resident(Base):
    __tablename__ = "residents"

    id = Column(Integer, primary_key=True, index=True)
    idm = Column(String, unique=True, index=True)
    name = Column(String)
    kana = Column(String)
    address = Column(String)
    tel = Column(String)
    family_count = Column(Integer)
    vulnerabilities = Column(JSON)  # {eld: 1, inf: 0, ...}
    medical = Column(String)
    allergy = Column(String)
    care_needed = Column(Integer)
    evacuation_type = Column(String)
    agree_info = Column(Integer)
    agree_board = Column(Integer)
    registered_at = Column(String)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
