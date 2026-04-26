from pydantic import BaseModel, ConfigDict

class base_dto(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)
