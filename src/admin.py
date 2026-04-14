from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from src.core.config import settings
from src.infrastructure.database.models import (
    GenerationPrice,
    Task,
    Transaction,
    User,
    WebhookDelivery,
)


class AdminAuth(AuthenticationBackend):
    """Simple secret-key based authentication for the admin panel."""

    async def login(self, request: Request) -> bool:
        form = await request.form()
        password = form.get("password", "")
        if password == settings.secret_key:
            request.session.update({"authenticated": True})
            return True
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return request.session.get("authenticated", False)


class UserAdmin(ModelView, model=User):
    column_list = [
        User.id,
        User.external_user_id,
        User.balance,
        User.created_at,
    ]
    column_searchable_list = [User.external_user_id]
    column_sortable_list = [User.balance, User.created_at]
    column_default_sort = ("created_at", True)
    can_create = False
    can_delete = False
    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-user"


class TaskAdmin(ModelView, model=Task):
    column_list = [
        Task.id,
        Task.user_id,
        Task.type,
        Task.status,
        Task.prompt,
        Task.cost,
        Task.created_at,
    ]
    column_searchable_list = [Task.prompt, Task.fal_request_id]
    column_sortable_list = [Task.status, Task.type, Task.cost, Task.created_at]
    column_default_sort = ("created_at", True)
    can_create = False
    can_delete = False
    name = "Task"
    name_plural = "Tasks"
    icon = "fa-solid fa-wand-magic-sparkles"


class TransactionAdmin(ModelView, model=Transaction):
    column_list = [
        Transaction.id,
        Transaction.user_id,
        Transaction.type,
        Transaction.amount,
        Transaction.task_id,
        Transaction.created_at,
    ]
    column_sortable_list = [Transaction.type, Transaction.amount, Transaction.created_at]
    column_default_sort = ("created_at", True)
    can_create = False
    can_edit = False
    can_delete = False
    name = "Transaction"
    name_plural = "Transactions"
    icon = "fa-solid fa-money-bill-transfer"


class GenerationPriceAdmin(ModelView, model=GenerationPrice):
    column_list = [
        GenerationPrice.id,
        GenerationPrice.generation_type,
        GenerationPrice.cost,
        GenerationPrice.updated_at,
    ]
    can_create = True
    can_delete = False
    name = "Price"
    name_plural = "Prices"
    icon = "fa-solid fa-tags"


class WebhookDeliveryAdmin(ModelView, model=WebhookDelivery):
    column_list = [
        WebhookDelivery.id,
        WebhookDelivery.task_id,
        WebhookDelivery.url,
        WebhookDelivery.status,
        WebhookDelivery.attempts,
        WebhookDelivery.response_code,
        WebhookDelivery.last_attempt_at,
    ]
    column_sortable_list = [WebhookDelivery.status, WebhookDelivery.attempts]
    column_default_sort = ("created_at", True)
    can_create = False
    can_delete = False
    name = "Webhook Delivery"
    name_plural = "Webhook Deliveries"
    icon = "fa-solid fa-paper-plane"


def setup_admin(app, engine) -> Admin:
    auth_backend = AdminAuth(secret_key=settings.secret_key)
    admin = Admin(
        app,
        engine,
        authentication_backend=auth_backend,
        title="AI Generator Admin",
    )
    admin.add_view(UserAdmin)
    admin.add_view(TaskAdmin)
    admin.add_view(TransactionAdmin)
    admin.add_view(GenerationPriceAdmin)
    admin.add_view(WebhookDeliveryAdmin)
    return admin
