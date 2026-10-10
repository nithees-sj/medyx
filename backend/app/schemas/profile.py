import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, computed_field

from app.services.profiles import age_on


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str
    relationship: str
    dob: date
    sex: str
    blood_group: str
    emergency_contact_name: str | None
    emergency_contact_phone: str | None
    healththread_id: str
    record_version: int
    created_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def age(self) -> int:
        return age_on(self.dob)


class ProfileSummaryOut(ProfileOut):
    active_alerts: int = 0
    critical_alerts: int = 0
    documents: int = 0
    pending_review: int = 0
