from pydantic import BaseModel


class TownshipOut(BaseModel):
    uid: str
    code: str | None
    name: str
    name_my: str | None

    model_config = {"from_attributes": True}


class WardOut(BaseModel):
    uid: str
    code: str | None
    name: str
    name_my: str | None

    model_config = {"from_attributes": True}


class VillageOut(BaseModel):
    uid: str
    code: str | None
    name: str
    name_my: str | None

    model_config = {"from_attributes": True}


class ICD10Out(BaseModel):
    uid: str
    code: str | None
    icd_code: str | None
    name: str

    model_config = {"from_attributes": True}


class ICD10Page(BaseModel):
    page: int
    limit: int
    total: int
    results: list[ICD10Out]
