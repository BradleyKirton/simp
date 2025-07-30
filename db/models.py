from django.db import models
from django.contrib.postgres import fields as pgfields
from django.db.models import expressions as db_expressions

DEFAULT_VERSION = 1


class DbError(Exception): ...


class OptimisticUpdateError(DbError): ...


class Customer(models.Model):
    """Models a customer."""

    name = models.CharField(blank=True, max_length=255)
    address = models.TextField(blank=True)
    version = models.IntegerField(db_default=DEFAULT_VERSION, default=DEFAULT_VERSION)
    sys_period = pgfields.DateTimeRangeField(
        db_default=db_expressions.RawSQL("TSTZRANGE(CURRENT_TIMESTAMP, null)", [])
    )

    class Meta:
        verbose_name = "Customer"
        verbose_name_plural = "Customers"
        constraints = [
            models.CheckConstraint(
                name="cst_version_gt_0", condition=models.Q(version__gt=0)
            )
        ]

    @classmethod
    def new(cls, name: str, address: str) -> "Customer":
        return Customer.objects.create(name=name, address=address)

    def update(self, name: str, address: str) -> None:
        customer_id = self.pk
        update_count = Customer.objects.filter(
            id=customer_id, version=self.version
        ).update(name=name, address=address)

        if update_count != 1:
            raise OptimisticUpdateError(f"Failed to update customer {customer_id}")

        self.refresh_from_db()


class CustomerHistory(models.Model):
    """Models customer history."""

    hid = models.BigAutoField(primary_key=True)

    # Customer model fields
    id = models.BigIntegerField()
    name = models.CharField(null=True)
    address = models.TextField(null=True)
    version = models.IntegerField(null=True)
    sys_period = pgfields.DateTimeRangeField()

    class Meta:
        verbose_name = "Customer (History)"
        verbose_name_plural = "Customers (History)"
        indexes = [models.Index(fields=["sys_period"], name="csth_sys_period_idx")]


class Message(models.Model):
    """Models a chat message."""

    user = models.CharField()
    content = models.TextField()
    sent_after = models.DateTimeField(null=True)
    sent_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(
        db_default=db_expressions.RawSQL("CURRENT_TIMESTAMP", [])
    )

    class Meta:
        verbose_name = "Message"
        verbose_name_plural = "Messages"
