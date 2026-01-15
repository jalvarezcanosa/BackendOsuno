import json
import secrets
from json import JSONDecodeError

import bcrypt
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import User, UserSession
from django.utils.crypto import get_random_string
from django.views.decorators.csrf import csrf_exempt

from osunorest01app.models import UserSession, User, Game

@csrf_exempt
def users(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'HTTP method not supported'}, status=400)

@csrf_exempt
def health_check(request):
    return JsonResponse({"is_alive": True}, status=200)

def __get_request_user(request):
    header_token = request.headers.get('Api-Session-Token', None)
    if header_token is None:
        return None
    try:
        db_session = UserSession.objects.get(token=header_token)
        return db_session.user
    except UserSession.DoesNotExist:
        return None

@csrf_exempt
def create_user(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'HTTP method not supported'}, status=405)
    try:
        body_json = json.loads(request.body)
        username = body_json['username']
        password = body_json['password']


    except (json.JSONDecodeError, KeyError):
        return JsonResponse({"error": "Missing parameter"}, status=400)
    if User.objects.filter(username=username).exists():
        return JsonResponse({"error": "User already exists"}, status=409)
    hashed_password = bcrypt.hashpw(password.encode('utf8'), bcrypt.gensalt()).decode('utf8')
    user = User(username=username, encrypted_password=hashed_password)
    user.save()
    return JsonResponse({"success": True, "username": username}, status=201)


@csrf_exempt
def create_room(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'HTTP method not supported'}, status=400)

    token = request.headers.get('Session')

    if not token:
        return JsonResponse({'error': 'Invalid token'}, status=401)

    try:
        session = UserSession.objects.get(token=token)
        current_user = session.user
    except UserSession.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)

    while True:
        room_code = get_random_string(length=3, allowed_chars='ABCDEFGHIJKLMNOPQRSTUVWXYZ')
        if not Game.objects.filter(code=room_code).exists():
            break

    try:
        new_game = Game.objects.create(
            code = room_code,
            state="room_not_started",
            creator=current_user,
        )

        return JsonResponse({"roomCode": new_game.code}, status=201)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

