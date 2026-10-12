from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DatasetUploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    original_filename: str
    row_count: int
    column_count: int
