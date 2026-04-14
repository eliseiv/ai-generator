from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import GenerationPrice, GenerationType


class SQLAlchemyPriceRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_cost(self, generation_type: GenerationType) -> Decimal:
        stmt = select(GenerationPrice.cost).where(
            GenerationPrice.generation_type == generation_type
        )
        result = await self._session.execute(stmt)
        cost = result.scalar_one_or_none()
        if cost is None:
            return self._default_cost(generation_type)
        return cost

    async def ensure_defaults(self) -> None:
        """Insert default prices if they don't exist."""
        defaults = {
            GenerationType.TEXT_TO_IMAGE: Decimal("10.00"),
            GenerationType.IMAGE_TO_IMAGE: Decimal("10.00"),
            GenerationType.TEXT_TO_VIDEO: Decimal("50.00"),
            GenerationType.IMAGE_TO_VIDEO: Decimal("50.00"),
        }
        for gen_type, cost in defaults.items():
            existing = await self._session.execute(
                select(GenerationPrice).where(GenerationPrice.generation_type == gen_type)
            )
            if existing.scalar_one_or_none() is None:
                self._session.add(GenerationPrice(generation_type=gen_type, cost=cost))
        await self._session.flush()

    @staticmethod
    def _default_cost(generation_type: GenerationType) -> Decimal:
        defaults = {
            GenerationType.TEXT_TO_IMAGE: Decimal("10.00"),
            GenerationType.IMAGE_TO_IMAGE: Decimal("10.00"),
            GenerationType.TEXT_TO_VIDEO: Decimal("50.00"),
            GenerationType.IMAGE_TO_VIDEO: Decimal("50.00"),
        }
        return defaults.get(generation_type, Decimal("10.00"))
