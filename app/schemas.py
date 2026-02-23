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
