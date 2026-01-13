import json
import secrets
from json import JSONDecodeError

import bcrypt
from django.http import JsonResponse
from django.utils.crypto import get_random_string
from django.views.decorators.csrf import csrf_exempt

from osunorest01app.models import UserSession, User, Room, Game

@csrf_exempt
def users(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'HTTP method not supported'}, status=400)

    try:
        body_json = json.loads(request.body)
    except json.decoder.JSONDecodeError:
        return JsonResponse({"error": "Missing parameter"}, status=400)

    try:
        username_json =body_json['username']
        password_json =body_json['password']
    except KeyError:
        return JsonResponse({"error": "Missing parameter"}, status=400)

    if User.objects.filter(username=username_json).exists():
        return JsonResponse({"error": "User already exists"}, status=409)

    salted_and_hashed_pass = bcrypt.hashpw(password_json.encode('utf8'), bcrypt.gensalt()).decode('utf8')
    user_object = User(username=username_json, encrypted_password=salted_and_hashed_pass)
    user_object.save()
    return JsonResponse({"is_created": True}, status=201)

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

    room_code = ""
    while True:
        room_code = get_random_string(length=3, allowed_chars='ABCDEFGHIJKLMNOPQRSTUVWXYZ')
        if not Room.objects.filter(code=room_code).exists():
            break

    try:
        new_room = Room.objects.create(code=room_code)

        Game.objects.create(
            state="room_not_started",
            creator=current_user,
            join=new_room
        )

        return JsonResponse({"roomCode": new_room.code}, status=201)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

