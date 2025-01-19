# Sage Santomenna 2023, 2025
# models used by sqlalchemy to understand the database
import os, sys
import json
from typing import List

import sqlalchemy
from sqlalchemy import select, insert, and_, or_
from sqlalchemy import Column, Integer, String, ForeignKey, Table, PrimaryKeyConstraint
from sqlalchemy.orm import relationship, Mapped, mapped_column

from sqlalchemy import create_engine, Column, Integer, String, Numeric, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

grandparentDir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir))
sys.path.append(grandparentDir)

from scheduleLib.db.dbConfig import candidate_base as Base, mapper_registry
sys.path.remove(grandparentDir)

# codes to be used for processing. if you change these, you need to recreate the db
codes = {
    0: "Not processed",
    1: "Autoprocess success",
    2: "Manual processing success",
    3: "Manual processing success (altered PSF threshold)",
    101: "Testing code",
    -1: "Autoprocess nominal (no target, previously “fail”)",
    -2: "Not in FOV",
    -3: "Not enough reference stars",
    -4: "Failed in frame re-registration (at least five tries)",
    -5: "Failed astrometric solution",
    -6: "Autoprocess false positive",
    -7: "Failed to generate report",
    -8: "Ambiguous in FOV",
    -9: "Unknown",
    -10: "Processing Crash",
    -11: "Other",
    -12: "Will not be processed"
}

# table to match observations with obs codes
ObservationCodeAssociation = Table(
    'ObservationCodeAssociation',
    Base.metadata,
    Column('ObservationID', Integer, ForeignKey('Observation.ObservationID'), nullable=False),
    Column('ProcessingCodeID', Integer, ForeignKey('ProcessingCode.ID'), nullable=False),
    PrimaryKeyConstraint('ObservationID', 'ProcessingCodeID')
)

# model for the candidate (target) object
class CandidateModel(Base):
    __tablename__ = 'Candidates'

    ID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    Author = Column(String, nullable=False)
    DateAdded = Column(String, nullable=False)
    DateLastEdited = Column(String)
    CandidateName = Column(String, nullable=False)
    Priority = Column(Integer, nullable=False)
    CandidateType = Column(String, nullable=False)
    SchedulingType = Column(String, nullable=False)
    Updated = Column(String)
    StartObservability = Column(String)
    EndObservability = Column(String)
    TransitTime = Column(String)
    RejectedReason = Column(String)
    RemovedReason = Column(String)
    RemovedDt = Column(String)
    RA = Column(Numeric)
    Dec = Column(Numeric)
    Magnitude = Column(Numeric)
    Info: Mapped[List["Info"]] = relationship("Info", back_populates="candidate")
    SchedulingCfg = relationship("SchedulingCfg", back_populates="candidate",uselist=False)
    ObservingCfg = relationship("ObservingCfg", back_populates="candidate",uselist=False)
    # Status = relationship("Status", back_populates="candidate")
    Observations: Mapped[List["Observation"]] = relationship("Observation", back_populates="candidate")

    def __repr__(self):
        return f"<CandidateModel(CandidateName={self.CandidateName}, CandidateType={self.CandidateType})>"
    
    def __str__(self):
        s = f"{self.CandidateName} ({self.CandidateType})\n"
        s += f"  RA: {self.RA}, Dec: {self.Dec}\n"
        s += f"  Magnitude: {self.Magnitude}\n"
        s += f"  Observability: {self.StartObservability} - {self.EndObservability}\n"
        s += f"  Rejected: {self.RejectedReason if self.RejectedReason is not None else False}\n"
        s += f"  Removed: {self.RejectedReason if self.RejectedReason is not None else False}\n"
        s += f"  Scheduling Configuration: {self.SchedulingCfg}\n"
        s += f"  Observing Configuration: {self.ObservingCfg}\n"
        s += f"  Observations: {len(self.Observations)}\n"
        if len(self.Info) > 0:
            s += "  Info:\n"
            for i in self.Info:
                s += f"    {i}\n"
        return s

    def as_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class Info(Base):
    __tablename__ = 'Info'

    CandidateID = Column(Integer, ForeignKey('Candidates.ID'))
    ID = Column(Integer, primary_key=True, autoincrement=True)
    Key = Column(String, nullable=False)
    Value = Column(String, nullable=False)
    candidate = relationship('CandidateModel', back_populates='Info')

    def __repr__(self):
        return f"<Info(Key={self.Key}, Value={self.Value})>"
    def __str__(self):
        return f"{self.Key}: {self.Value}"

    def as_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class SchedulingCfg(Base):
    __tablename__ = 'SchedulingCfg'

    CandidateID = Column(Integer, ForeignKey('Candidates.ID'),unique=True)
    ID = Column(Integer, primary_key=True, autoincrement=True)
    # Key = Column(String, nullable=False)
    cfg = Column(String, nullable=False)
    candidate = relationship('CandidateModel', back_populates='SchedulingCfg')

    def __repr__(self):
        return f"<SchedulingCfg(config={self.cfg})>"
    
    def __str__(self):
        return self.cfg
    
    @property
    def config(self):
        return json.loads(self.cfg)
    
    def as_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class ObservingCfg(Base):
    __tablename__ = 'ObservingCfg'

    CandidateID = Column(Integer, ForeignKey('Candidates.ID'),unique=True)
    ID = Column(Integer, primary_key=True, autoincrement=True)
    # Key = Column(String, nullable=False)
    cfg = Column(String, nullable=False)
    candidate = relationship('CandidateModel', back_populates='ObservingCfg')

    def __repr__(self):
        return f"<ObservingCfg(config={self.cfg})>"
    
    def __str__(self):
        return self.cfg
    
    @property
    def config(self):
        return json.loads(self.cfg)
    
    def as_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


# model for the observation object
class Observation(Base):
    __tablename__ = 'Observation'

    CandidateID = Column(Integer, ForeignKey('Candidates.ID'))
    ObservationID = Column(Integer, primary_key=True, nullable=False)
    # RMSE_RA = Column(Numeric)
    # RMSE_Dec = Column(Numeric)
    RA = Column(Numeric)
    Dec = Column(Numeric)
    # ApproachColor = Column(String)
    # AstrometryStatus = Column(String)
    ExposureTime = Column(Numeric)
    EncoderRA = Column(Numeric)
    EncoderDec = Column(Numeric)
    # SkyBackground = Column(Numeric)
    # Temperature = Column(Numeric)
    Dataset = Column(String)
    CaptureStartEpoch = Column(Numeric)
    Focus = Column(Numeric)
    RAOffset = Column(Numeric) # deg
    DecOffset = Column(Numeric) # deg
    SystemName = Column(String)
    CameraName = Column(String)
    # ProcessingCodesCol = Column(String)
    Submitted = Column(Integer, nullable=False)
    Comments = Column(Text)

    candidate = relationship('CandidateModel', back_populates='Observations')
    ProcessingCode: Mapped[List["ProcessingCode"]] = relationship("ProcessingCode", secondary='ObservationCodeAssociation', back_populates="Observations")

    def as_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

# model for the processing code
class ProcessingCode(Base):
    __tablename__ = 'ProcessingCode'

    ID = Column(Integer, primary_key=True, autoincrement=True)
    Code = Column(Integer, nullable=False, unique=True)
    Description = Column(String, nullable=False)
    Observations: Mapped[List["Observation"]] = relationship("Observation", secondary='ObservationCodeAssociation', back_populates="ProcessingCode")

    def as_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}