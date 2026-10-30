from django.shortcuts import render
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db import connection
from django.db.models import Q
from rest_framework import viewsets
from .models import Category, Dish, PlacesUsage
from django.db.models import F, Sum
from .serializers import (
    CategorySerializer, DishSerializer, SignupSerializer, LoginSerializer,
    ProfileSerializer, ChangePasswordSerializer, SearchResultSerializer,
)
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, action, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from . import placing
import os
import requests
from django.utils import timezone

# Create your views here.
@api_view(["GET"])
def hello(request):
    return Response({"message": "Food ranker API is alive"})

class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer

    def get_queryset(self):
        return Category.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        last = self.get_queryset().order_by("-position").first()
        serializer.save(owner=self.request.user, position=(last.position + 1) if last else 0)

    @action(detail=False, methods=["post"])
    def reorder(self, request):
        order = request.data.get("order", [])
        if not isinstance(order, list):
            return Response({"error": "order must be a list of category ids"}, status=400)
        for position, category_id in enumerate(order):
            self.get_queryset().filter(pk=category_id).update(position=position)
        return Response({"ok": True})

class DishViewSet(viewsets.ModelViewSet):
    serializer_class = DishSerializer

    def get_queryset(self):
        dishes = Dish.objects.filter(category__owner=self.request.user)
        category = self.request.query_params.get("category")
        if category:
            dishes = dishes.filter(category_id=category)
        return dishes
    
    def perform_destroy(self, instance):
        category = instance.category
        instance.delete()
        placing.record_ranks(category)
        
    @action(detail=True, methods=["post"])
    def place(self, request, pk=None):
        dish = self.get_object()
        answers = request.data.get("answers", [])
        if not isinstance(answers, list) or any(a not in ("win", "lose", "tie") for a in answers):
            return Response({"error": "answers must be a list of win, lose or tie"}, status=400)

        others = list(Dish.objects.filter(category=dish.category).exclude(pk=dish.pk))
        step, value = placing.next_step(others, answers)

        if step == "ask":
            opponent = DishSerializer(others[value], context={"request": request}).data
            return Response({"done": False, "round": len(answers) + 1, "opponent": opponent})

        dish.elo = placing.score_for_position(others, value)
        dish.save()
        placing.record_ranks(dish.category)
        return Response({
            "done": True,
            "rank": value + 1,
            "total": len(others) + 1,
            "dish": DishSerializer(dish, context={"request": request}).data,
        })

    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        dish = self.get_object()
        try:
            position = int(request.data.get("position"))
        except (TypeError, ValueError):
            return Response({"error": "position must be a number"}, status=400)
        placing.move_dish(dish, position)
        dish.refresh_from_db()
        return Response(DishSerializer(dish, context={"request": request}).data)

    @action(detail=False, methods=["post"])
    def order(self, request):
        category = Category.objects.filter(pk=request.data.get("category"), owner=request.user).first()
        ids = request.data.get("order", [])
        if not category or not isinstance(ids, list):
            return Response({"error": "category and order are required"}, status=400)
        if set(ids) != set(category.dishes.values_list("id", flat=True)):
            return Response({"error": "order must list every dish in the category"}, status=400)
        placing.apply_order(category, ids)
        return Response({"ok": True})

def user_data(user):
    return {"id": user.id, "email": user.username, "display_name": user.first_name}


@api_view(["POST"])
@permission_classes([AllowAny])
def signup(request):
    serializer = SignupSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    user = User.objects.create_user(
        username=data["email"],
        email=data["email"],
        password=data["password"],
        first_name=data["display_name"],
    )
    token, _ = Token.objects.get_or_create(user=user)
    return Response({"token": token.key, "user": user_data(user)}, status=201)


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = authenticate(
        username=serializer.validated_data["email"].strip().lower(),
        password=serializer.validated_data["password"],
    )
    if user is None:
        return Response({"error": "Wrong email or password."}, status=400)
    token, _ = Token.objects.get_or_create(user=user)
    return Response({"token": token.key, "user": user_data(user)})


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def me(request):
    if request.method == "PATCH":
        serializer = ProfileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request.user.first_name = serializer.validated_data["display_name"]
        request.user.save(update_fields=["first_name"])
    return Response(user_data(request.user))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request):
    Token.objects.filter(user=request.user).delete()
    return Response({"ok": True})

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_password(request):
    serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    if not request.user.check_password(serializer.validated_data["current_password"]):
        return Response({"current_password": ["That is not your current password."]}, status=400)
    request.user.set_password(serializer.validated_data["new_password"])
    request.user.save()
    Token.objects.filter(user=request.user).delete()
    token = Token.objects.create(user=request.user)
    return Response({"token": token.key})

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def delete_account(request):
    password = request.data.get("password", "")
    if not request.user.check_password(password):
        return Response({"password": ["Incorrect password."]}, status=400)
    request.user.delete()
    return Response({"ok": True})

@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return Response({"ok": True})

@api_view(["GET"])
def search(request):
    q = request.query_params.get("q", "").strip()
    if not q:
        return Response({"categories": [], "dishes": []})
    categories = Category.objects.filter(owner=request.user, name__icontains=q)[:10]
    dishes = (
        Dish.objects.filter(category__owner=request.user)
        .filter(Q(restaurant__icontains=q) | Q(name__icontains=q) | Q(note__icontains=q))
        .select_related("category")[:50]
    )
    context = {"request": request, "q": q}
    return Response({
        "categories": CategorySerializer(categories, many=True, context=context).data,
        "dishes": SearchResultSerializer(dishes, many=True, context=context).data,
    })

PLACES_URL = "https://places.googleapis.com/v1/places:autocomplete"

def allow_lookup():
    daily = int(os.environ.get("PLACES_DAILY_LIMIT", "400"))
    monthly = int(os.environ.get("PLACES_MONTHLY_LIMIT", "9000"))
    today = timezone.localdate()
    month_total = (
        PlacesUsage.objects.filter(day__year=today.year, day__month=today.month)
        .aggregate(total=Sum("count"))["total"] or 0
    )
    if month_total >= monthly:
        return False
    usage, _ = PlacesUsage.objects.get_or_create(day=today)
    updated = PlacesUsage.objects.filter(pk=usage.pk, count__lt=daily).update(count=F("count") + 1)
    return updated == 1

@api_view(["GET"])
def place_suggestions(request):
    q = request.query_params.get("q", "").strip()
    if len(q) < 3:
        return Response([])

    if request.query_params.get("source") != "google":
        rows = (
            Dish.objects.filter(category__owner=request.user, restaurant__icontains=q)
            .order_by("restaurant")
            .values("restaurant", "place_id")
            .distinct()
        )
        seen = {}
        for row in rows:
            name = row["restaurant"]
            current = seen.get(name.lower())
            if current is None or (row["place_id"] and not current["place_id"]):
                seen[name.lower()] = {
                    "place_id": row["place_id"], "name": name, "address": "", "saved": True,
                }
        if seen:
            return Response(list(seen.values())[:5])

    key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not key or not allow_lookup():
        return Response([])

    try:
        res = requests.post(
            PLACES_URL,
            json={
                "input": q,
                "languageCode": "en",
                "includedRegionCodes": ["in"],
                "includedPrimaryTypes": ["restaurant", "cafe", "bakery", "meal_takeaway", "fast_food_restaurant"],
            },
            headers={"X-Goog-Api-Key": key},
            timeout=5,
        )
        res.raise_for_status()
    except requests.RequestException:
        return Response([])

    items = []
    for suggestion in res.json().get("suggestions", []):
        prediction = suggestion.get("placePrediction")
        if not prediction:
            continue
        text = prediction.get("structuredFormat", {})
        items.append({
            "place_id": prediction.get("placeId", ""),
            "name": text.get("mainText", {}).get("text", ""),
            "address": text.get("secondaryText", {}).get("text", ""),
            "saved": False,
        })
    return Response(items[:5])