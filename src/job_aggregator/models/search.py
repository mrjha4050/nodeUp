
from pydantic import BaseModel, Field
from .job import Job, JobType, ExperienceLevel, LocationType, SalaryRange, CompanyInfo

class ProviderResponse(BaseModel):

    provider_name: str = Field(..., description="Name of the job provider")
    jobs: list[Job] = Field(..., description="List of job postings from the provider")
    total_results: int = Field(..., description="Total number of job postings found")
    success: bool = Field(..., description="Indicates if the provider responded successfully")
    error_message: str | None = Field(None, description="Error message if the provider failed to respond")
    description: str | None = Field(None, description="Description of the provider or the response")


class SearchRequest(BaseModel):
    """Request model for job search queries."""

    query: str = Field(..., description="Search query string")
    location: str | None = Field(None, description="Location filter for the search")
    job_type: JobType | None = Field(None, description="Filter by job type")
    experience_level: ExperienceLevel | None = Field(None, description="Filter by experience level")
    location_type: LocationType | None = Field(None, description="Filter by location type")
    salary_range: SalaryRange | None = Field(None, description="Filter by salary range")
    limited_results: int | None = Field(None, description="Limit the number of results returned")
    offset: int | None = Field(None, description="Offset for paginated results")
    skills: list[str] | None = Field(None, description="Filter by required skills")


class SearchResponse(BaseModel):
    """Response model for job search results."""

    query: str = Field(..., description="Search query string")
    location: str | None = Field(None, description="Location filter for the search")
    jobs : list[Job] = Field(..., description="List of job postings found")
    job_type: JobType | None = Field(None, description="Filter by job type")
    skills: list[str] | None = Field(None, description="Filter by required skills")
    total_results: int = Field(..., description="Total number of job postings found across all providers")
    providers: list[ProviderResponse] = Field(..., description="List of provider responses with job postings")
    error_messages: list[str] = Field(..., description="List of error messages from providers that failed to respond")