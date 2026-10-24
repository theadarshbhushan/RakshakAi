"""
Tenant-Scoped Repository Base for strict multi-tenant isolation.
Automatically injects the authenticated principal's org_id into all database queries and mutations.
Accessing another tenant's resource returns a 404 NotFoundError to prevent existence enumeration.
"""
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar

from beanie import Document, PydanticObjectId

from app.core.errors import ForbiddenError, NotFoundError

T = TypeVar("T", bound=Document)


class TenantScopedRepository(Generic[T]):
    def __init__(self, model_class: Type[T], org_id: str) -> None:
        if not org_id:
            raise ForbiddenError("Tenant context (org_id) is required to access tenant-scoped resources.")
        self.model_class = model_class
        self.org_id = str(org_id)

    def _scope_query(self, query: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        scoped = {"org_id": self.org_id}
        if query:
            scoped.update(query)
        return scoped

    async def get_by_id(self, doc_id: Any) -> T:
        """
        Fetch document by ID, strictly enforcing org_id ownership.
        Returns 404 if not found or belongs to another tenant.
        """
        try:
            obj_id = PydanticObjectId(doc_id) if isinstance(doc_id, str) and len(doc_id) == 24 else doc_id
        except Exception:
            obj_id = doc_id

        doc = await self.model_class.find_one({"_id": obj_id, "org_id": self.org_id})
        if not doc:
            raise NotFoundError(self.model_class.__name__, doc_id)
        return doc

    async def find_one(self, query: Optional[Dict[str, Any]] = None) -> Optional[T]:
        """Find single document within this tenant organization."""
        return await self.model_class.find_one(self._scope_query(query))

    async def find_all(
        self,
        query: Optional[Dict[str, Any]] = None,
        sort_by: Optional[str] = "-_id",
        limit: int = 50,
        skip: int = 0,
    ) -> List[T]:
        """Find list of documents strictly belonging to this tenant organization."""
        scoped_q = self._scope_query(query)
        cursor = self.model_class.find(scoped_q)
        if sort_by:
            cursor = cursor.sort(sort_by)
        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)
        return await cursor.to_list()

    async def count(self, query: Optional[Dict[str, Any]] = None) -> int:
        """Count documents belonging to this tenant organization."""
        return await self.model_class.find(self._scope_query(query)).count()

    async def insert(self, document: T) -> T:
        """Insert new document, validating that its org_id matches the tenant context."""
        if hasattr(document, "org_id"):
            document.org_id = self.org_id
        await document.insert()
        return document

    async def update(self, document: T) -> T:
        """Update existing document, verifying org_id ownership."""
        if getattr(document, "org_id", None) != self.org_id:
            raise NotFoundError(self.model_class.__name__, getattr(document, "id", ""))
        await document.save()
        return document

    async def delete(self, document: T) -> None:
        """Delete document, verifying org_id ownership."""
        if getattr(document, "org_id", None) != self.org_id:
            raise NotFoundError(self.model_class.__name__, getattr(document, "id", ""))
        await document.delete()
