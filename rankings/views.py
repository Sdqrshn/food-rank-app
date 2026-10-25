from django.shortcuts import render
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework import viewsets
from .models import Category, Dish
from .serializers import (
    CategorySerializer, DishSerializer, SignupSerializer, LoginSerializer,
    ProfileSerializer, ChangePasswordSerializer,
)
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, action, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from . import placing

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