import functools

def transactional(fn):
    @functools.wraps(fn)
    async def wrapper(self, *args, **kwargs):
        # prefer self.session; fall back to self.repo.session for old callers
        session = getattr(self, "session", None) or getattr(getattr(self, "repo", None), "session", None)
        if session is None:
            raise RuntimeError("No session found on service for transactional()")
        try:
            result = await fn(self, *args, **kwargs)
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise
    return wrapper
