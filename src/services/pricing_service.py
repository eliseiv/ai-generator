from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import GenerationType
from src.infrastructure.database.repositories.price_repo import SQLAlchemyPriceRepository


async def get_generation_cost(session: AsyncSession, generation_type: GenerationType) -> Decimal:
    repo = SQLAlchemyPriceRepository(session)
    return await repo.get_cost(generation_type)
