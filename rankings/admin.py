from django.contrib import admin
from .models import Category, Dish, RankHistory, PlacesUsage

# Register your models here.
admin.site.register(Category)
admin.site.register(Dish)
admin.site.register(RankHistory)
admin.site.register(PlacesUsage)