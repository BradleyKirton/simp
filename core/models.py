from django.db import models
from django.contrib.postgres import fields as pgfields
from django.db.models import expressions as db_expressions


class Customer(models.Model):
    name = models.CharField(blank=True, max_length=255)
    address = models.TextField(blank=True)
    version = models.IntegerField(db_default="1", default=1)
    sys_period = pgfields.DateTimeRangeField(
        db_default=db_expressions.RawSQL("tstzrange(current_timestamp, null)", [])
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
        update_count = Customer.objects.filter(id=self.pk).update(
            name=name, address=address
        )

        if update_count != 1:
            raise Exception(":(")

        self.refresh_from_db()


class CustomerHistory(models.Model):
    hid = models.BigAutoField(primary_key=True)
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
    name = models.CharField()
    content = models.TextField()
    sent_after = models.DateTimeField(null=True)
    sent_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(
        db_default=db_expressions.RawSQL("CURRENT_TIMESTAMP", [])
    )

    class Meta:
        verbose_name = "Message"
        verbose_name_plural = "Messages"
