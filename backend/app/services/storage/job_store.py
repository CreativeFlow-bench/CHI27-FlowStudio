from uuid import UUID, uuid4

from app.models import CandidateRequest, JobStatus, LegacyJobRecord


class InMemoryJobStore:
    def __init__(self) -> None:
        self._jobs: dict[UUID, LegacyJobRecord] = {}

    def create(self, request: CandidateRequest) -> LegacyJobRecord:
        job = LegacyJobRecord(job_id=uuid4(), status=JobStatus.queued, request=request)
        self._jobs[job.job_id] = job
        return job

    def get(self, job_id: UUID) -> LegacyJobRecord | None:
        return self._jobs.get(job_id)

    def save(self, job: LegacyJobRecord) -> LegacyJobRecord:
        self._jobs[job.job_id] = job
        return job
