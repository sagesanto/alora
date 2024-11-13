# Sage Santomenna 2023
# models used by sqlalchemy to understand the database
from typing import List

import sqlalchemy
from sqlalchemy import select, insert, and_, or_
from sqlalchemy import Column, Integer, String, ForeignKey, Table, PrimaryKeyConstraint
from sqlalchemy.orm import relationship, Mapped, mapped_column

from sqlalchemy import create_engine, Column, Integer, String, Numeric, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
import os, sys

grandparentDir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir))
sys.path.append(grandparentDir)

from scheduleLib.db.dbConfig import Base
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
    Updated = Column(String)
    StartObservability = Column(String)
    EndObservability = Column(String)
    TransitTime = Column(String)
    RejectedReason = Column(String)
    RemovedReason = Column(String)
    RemovedDt = Column(String)
    RA = Column(Numeric)
    Dec = Column(Numeric)
    dRA = Column(Numeric)
    dDec = Column(Numeric)
    Magnitude = Column(Numeric)
    RMSE_RA = Column(Numeric)
    RMSE_Dec = Column(Numeric)
    nObs = Column(Integer)
    Score = Column(Integer)
    ApproachColor = Column(String)
    ExposureTime = Column(Numeric)
    NumExposures = Column(Integer)
    Scheduled = Column(Integer, default=0)
    Observed = Column(Integer, default=0)
    Processed = Column(Numeric, default=0)
    Submitted = Column(Integer, default=0)
    Notes = Column(Text)
    CVal1 = Column(Text)
    CVal2 = Column(Text)
    CVal3 = Column(Text)
    CVal4 = Column(Text)
    CVal5 = Column(Text)
    CVal6 = Column(Text)
    CVal7 = Column(Text)
    CVal8 = Column(Text)
    CVal9 = Column(Text)
    CVal10 = Column(Text)
    Filter = Column(String)
    Observations: Mapped[List["Observation"]] = relationship("Observation", back_populates="candidate")

    def as_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

# model for the observation object
class Observation(Base):
    __tablename__ = 'Observation'

    CandidateID = Column(Integer, ForeignKey('Candidates.ID'))
    ObservationID = Column(Integer, primary_key=True, nullable=False)
    RMSE_RA = Column(Numeric)
    RMSE_Dec = Column(Numeric)
    RA = Column(Numeric)
    Dec = Column(Numeric)
    ApproachColor = Column(String)
    AstrometryStatus = Column(String)
    ExposureTime = Column(Numeric)
    EncoderRA = Column(Numeric)
    EncoderDec = Column(Numeric)
    SkyBackground = Column(Numeric)
    Temperature = Column(Numeric)
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