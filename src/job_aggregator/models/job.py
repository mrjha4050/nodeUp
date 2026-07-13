

from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl

from enum  import StrEnum

class JobType(StrEnum):
    """Enumeration of job types."""

    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    TEMPORARY = "temporary"

class ExperienceLevel(StrEnum):
    """Enumeration of experience levels."""

    ENTRY = "entry"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    DIRECTOR = "director"
    EXECUTIVE = "executive"

class LocationType(StrEnum):
    """Enumeration of location types."""

    ONSITE = "onsite"
    REMOTE = "remote"
    HYBRID = "hybrid"

class SalaryRange(BaseModel):
    """Model representing a salary range."""

    min: float = Field(..., description="Minimum salary")
    max: float = Field(..., description="Maximum salary")
    currency: str = Field(..., description="Currency code (e.g., USD, EUR)")
    period: str = Field(..., description="Salary period (e.g., per year, per month)")

class CompanyInfo(BaseModel):
    """Model representing company information."""

    name: str = Field(..., description="Company name")
    website: HttpUrl = Field(..., description="Company website URL")
    industry: str = Field(..., description="Industry sector of the company")
    size: str = Field(..., description="Size of the company (e.g., 1-10, 11-50)")

class Job(BaseModel):
    """Model representing a job posting."""

    id: str = Field(..., description="Unique identifier for the job")
    title: str = Field(..., description="Job title")
    description: str = Field(..., description="Job description")
    type: JobType = Field(..., description="Type of job (full-time, part-time, etc.)")
    experience_level: ExperienceLevel = Field(..., description="Required experience level")
    location_type: LocationType = Field(..., description="Type of location (onsite, remote, hybrid)")
    location: str = Field(..., description="Location of the job (city, state, country)")
    salary_range: SalaryRange = Field(..., description="Salary range for the job")
    skills: list[str] = Field(..., description="List of required skills for the job")
    company_info: CompanyInfo = Field(..., description="Information about the company")
    posted_at: datetime = Field(..., description="Date and time when the job was posted")
    application_url: HttpUrl = Field(..., description="URL to apply for the job")
    raw_data: dict = Field(..., exclude=True, description="Raw data from the job provider, for debugging and reference")
    

