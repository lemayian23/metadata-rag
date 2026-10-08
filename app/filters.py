from sqlalchemy import and_, or_

from app.models import Document
from app.schemas import MetadataFilter


def build_filter_conditions(filters: MetadataFilter | None):
    if not filters:
        return []

    conditions = []

    if filters.category:
        conditions.append(Document.category == filters.category)

    if filters.author:
        conditions.append(Document.author == filters.author)

    if filters.location:
        conditions.append(Document.location == filters.location)

    if filters.source:
        conditions.append(Document.source == filters.source)

    if filters.tags:
        conditions.append(Document.tags.overlap(filters.tags))

    if filters.published_after:
        conditions.append(Document.published_at >= filters.published_after)

    if filters.published_before:
        conditions.append(Document.published_at <= filters.published_before)

    for key, value in filters.extra.items():
        conditions.append(Document.meta[key].astext == str(value))

    return conditions