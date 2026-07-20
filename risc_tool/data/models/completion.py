from pydantic import BaseModel, ConfigDict


class Completion(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True, validate_by_alias=True)

    caption: str
    value: str
    meta: str
    name: str
    score: int

    def to_dict(self) -> dict[str, str | int]:
        return {
            "caption": self.caption,
            "value": self.value,
            "meta": self.meta,
            "name": self.name,
            "score": self.score,
        }
