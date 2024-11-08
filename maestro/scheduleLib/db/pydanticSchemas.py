# Sage Santomenna 2023
from typing import Optional

from db_models import CandidateModel, ObservationModel
from sqlalchemy_to_pydantic import sqlalchemy_to_pydantic
from pydantic import BaseModel

# pydantic interface layer to create sqlalchemy models from input

class CandidateSchema(BaseModel):
    Author: str
    DateAdded: str
    DateLastEdited: Optional[str] = None
    CandidateName: str
    Priority: int
    CandidateType: str
    Updated: Optional[str] = None
    StartObservability: Optional[str] = None
    EndObservability: Optional[str] = None
    TransitTime: Optional[str] = None
    RejectedReason: Optional[str] = None
    RemovedReason: Optional[str] = None
    RemovedDt: Optional[str] = None
    RA: float
    Dec: float
    dRA: Optional[float] = None
    dDec: Optional[float] = None
    Magnitude: Optional[float] = None
    RMSE_RA: Optional[float] = None
    RMSE_Dec: Optional[float] = None
    nObs: Optional[int] = None
    Score: Optional[int] = None
    ApproachColor: Optional[str] = None
    ExposureTime: Optional[float] = None
    NumExposures: Optional[int] = None
    Scheduled: Optional[int] = 0
    Observed: Optional[int] = 0
    Processed: Optional[float] = 0.0
    Submitted: Optional[int] = 0
    Notes: Optional[str] = None
    CVal1: Optional[str] = None
    CVal2: Optional[str] = None
    CVal3: Optional[str] = None
    CVal4: Optional[str] = None
    CVal5: Optional[str] = None
    CVal6: Optional[str] = None
    CVal7: Optional[str] = None
    CVal8: Optional[str] = None
    CVal9: Optional[str] = None
    CVal10: Optional[str] = None
    Filter: Optional[str] = None
    Guide: Optional[int] = 1


class ObservationSchema(BaseModel):
    CandidateID: Optional[int] = None
    RMSE_RA: Optional[float] = None
    RMSE_Dec: Optional[float] = None
    RA: Optional[float] = None
    Dec: Optional[float] = None
    ApproachColor: Optional[str] = None
    RecenteringSuccess: Optional[str] = None
    EncoderRA: Optional[float] = None
    EncoderDec: Optional[float] = None
    SkyBackground: Optional[float] = None
    Temperature: Optional[float] = None
    Dataset: Optional[str] = None
    CaptureStartEpoch: Optional[float] = None
    SolvedRA: Optional[float] = None
    SolvedDec: Optional[float] = None
    ProcessingCode: int
    Submitted: int
    Comments: Optional[str] = None

# what am i doing here???
def observationSchemaToModel(o:ObservationSchema):
    return ObservationModel()