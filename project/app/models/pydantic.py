from datetime import datetime
from pydantic import BaseModel, AnyHttpUrl, ConfigDict


class SummaryPayloadSchema(BaseModel):
    url: AnyHttpUrl


class SummaryResponseSchema(SummaryPayloadSchema):
    id: int


class SummaryUpdatePayloadSchema(SummaryPayloadSchema):
    summary: str


class SummarySchema(BaseModel):
    id: int
    url: str
    summary: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)