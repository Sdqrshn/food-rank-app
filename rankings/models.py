from django.db import models
from datetime import date
from django.conf import settings
from django.db.models.signals import post_delete
from django.dispatch import receiver

# Create your models here.
class Category(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="categories", null=True
    )
    name = models.CharField(max_length=60)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="unique_category_name_per_owner"),
        ]

    def __str__(self):
        return self.name

class Dish(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="dishes")
    name = models.CharField(max_length=100, blank=True)
    restaurant = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    note = models.TextField(blank=True)
    date_tried = models.DateField(default=date.today)
    map_link = models.URLField(blank=True)
    place_id = models.CharField(max_length=255, blank=True)
    photo = models.ImageField(upload_to="dishes/", null=True, blank=True)
    elo = models.FloatField(default=1500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-elo", "id"]

    def __str__(self):
        return f"{self.restaurant} ({self.name})" if self.name else self.restaurant

class RankHistory(models.Model):
    dish = models.ForeignKey(Dish, on_delete=models.CASCADE, related_name="history")
    rank = models.PositiveIntegerField()
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["recorded_at", "id"]

@receiver(post_delete, sender=Dish)
def delete_dish_photo(sender, instance, **kwargs):
    if instance.photo:
        instance.photo.delete(save=False)

class PlacesUsage(models.Model):
    day = models.DateField(unique=True)
    count = models.PositiveIntegerField(default=0)