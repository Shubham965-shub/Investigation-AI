from sqlalchemy import Column, Integer, String, ForeignKey, Text
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class ArchetypeType(Base):
    __tablename__ = "archetype_type"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    archetypes = relationship("Archetype", back_populates="archetype_type")

class Archetype(Base):
    __tablename__ = "archetype"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    definition = Column(Text, nullable=True)
    archetype_type_id = Column(Integer, ForeignKey("archetype_type.id"), nullable=False)
    archetype_type = relationship("ArchetypeType", back_populates="archetypes")
    evidences = relationship("Evidence", back_populates="archetype")
    interview_questionnaires = relationship("InterviewQuestionnaire", back_populates="archetype")
    rci_plans = relationship("RciPlan", back_populates="archetype")

class Evidence(Base):
    __tablename__ = "evidence"
    id = Column(Integer, primary_key=True)
    description = Column(Text, nullable=False)
    archetype_id = Column(Integer, ForeignKey("archetype.id"), nullable=False)
    archetype = relationship("Archetype", back_populates="evidences")

class InterviewQuestionnaire(Base):
    __tablename__ = "interview_questionnaire"
    id = Column(Integer, primary_key=True)
    description = Column(Text, nullable=False)
    archetype_id = Column(Integer, ForeignKey("archetype.id"), nullable=False)
    archetype = relationship("Archetype", back_populates="interview_questionnaires")

class RciPlan(Base):
    __tablename__ = "rci_plan"
    id = Column(Integer, primary_key=True)
    archetype_id = Column(Integer, ForeignKey("archetype.id"), nullable=False)
    
    # Relationships
    archetype = relationship("Archetype", back_populates="rci_plans")
    sections = relationship("RciPlanSection", back_populates="rci_plan", cascade="all, delete-orphan")

class RciPlanSection(Base):
    __tablename__ = "rci_plan_section"
    id = Column(Integer, primary_key=True)
    rci_plan_id = Column(Integer, ForeignKey("rci_plan.id"), nullable=False)
    title = Column(Text, nullable=False)
    correlation = Column(Text, nullable=True) # section correlation column
    six_m_bucket = Column(Text, nullable=True) # 6M fishbone category: MATERIAL/METHOD/MACHINE/MEASUREMENT/MAN/ENVIRONMENT
    
    # Relationships
    rci_plan = relationship("RciPlan", back_populates="sections")
    tasks = relationship("RciPlanTask", back_populates="section", cascade="all, delete-orphan")

class RciPlanTask(Base):
    __tablename__ = "rci_plan_task"
    id = Column(Integer, primary_key=True)
    rci_plan_section_id = Column(Integer, ForeignKey("rci_plan_section.id"), nullable=False)
    description = Column(Text, nullable=False)
    
    # Relationships
    section = relationship("RciPlanSection", back_populates="tasks")