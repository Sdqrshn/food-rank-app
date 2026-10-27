from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("categories", views.CategoryViewSet, basename="category")
router.register("dishes", views.DishViewSet, basename="dish")

urlpatterns = [
    path("hello/", views.hello),
    path("", include(router.urls)),
    path("auth/signup/", views.signup),
    path("auth/login/", views.login_view),
    path("auth/me/", views.me),
    path("auth/logout/", views.logout_view),
    path("auth/change-password/", views.change_password),
    path("auth/delete-account/", views.delete_account),\
    path("health/", views.health),
    path("search/", views.search),
    path("places/autocomplete/", views.place_suggestions),
]