"""Private CV downloads retain candidate and recruiter ownership checks."""
import httpx
import pytest
from tests.test_recruiter_workspace import workspace, headers


@pytest.mark.asyncio
@pytest.mark.parametrize('actor,role,status', [
    ('user-a', 'candidate', 200), ('user-b', 'candidate', 403),
    ('hr-a', 'recruiter', 200), ('hr-b', 'recruiter', 403),
])
async def test_private_resume_download_uses_identity_before_storage(workspace, monkeypatch, actor, role, status):
    app, _ = workspace
    reads = []
    def download(db, key):
        reads.append(key)
        return b'%PDF-1.4 candidate CV'
    monkeypatch.setattr('app.routes.applications.download_from_supabase', download)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/api/v1/applications/app-a/resume/pdf', headers=headers(actor, role))
    assert response.status_code == status
    assert len(reads) == int(status == 200)
    if status == 200:
        assert response.content.startswith(b'%PDF')
        assert response.headers['content-type'] == 'application/pdf'


@pytest.mark.asyncio
async def test_cv_cannot_be_read_without_authentication(workspace, monkeypatch):
    app, _ = workspace
    def forbidden_storage_read(*args):
        raise AssertionError('Unauthenticated request reached private storage')
    monkeypatch.setattr('app.routes.applications.download_from_supabase', forbidden_storage_read)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/api/v1/applications/app-a/resume/pdf')
    assert response.status_code == 401
