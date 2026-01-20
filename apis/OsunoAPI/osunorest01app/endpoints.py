import json
import secrets
import bcrypt
from django.http import JsonResponse
from django.utils.crypto import get_random_string
from django.views.decorators.csrf import csrf_exempt
from .models import User, UserSession, Game

@csrf_exempt
def health_check(request):
    return JsonResponse({"is_alive": True}, status=200)

def __get_request_user(request):
    header_token = request.headers.get('Session', None)
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
def login(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'HTTP method not supported'}, status=405)
    try:
        body = json.loads(request.body)
        username = body['username']
        password = body['password']
    except (json.JSONDecodeError, KeyError):
        return JsonResponse({"error": "Missing parameter"}, status=400)
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        return JsonResponse({"error": "User not found"}, status=404)
    if not bcrypt.checkpw(
        password.encode('utf8'),
        user.encrypted_password.encode('utf8')):
        return JsonResponse({"error": "Password not valid"}, status=401)
    token = secrets.token_hex(16)
    UserSession.objects.create(user=user, token=token)
    return JsonResponse(
        {"sessionToken": token}, status=201)

@csrf_exempt
def get_me(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'HTTP method not supported'}, status=405)

    user = __get_request_user(request)
    if user is None:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    games_won = Game.objects.filter(creator=user, state='creator_won').count()
    games_won += Game.objects.filter(joined=user, state='joined_won').count()

    games_played = Game.objects.filter(creator=user).count()
    games_played += Game.objects.filter(joined=user).count()

    return JsonResponse({
        "username": user.username,
        "gamesWon": games_won,
        "gamesPlayed": games_played
    }, status=200)


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

    last_game = Game.objects.last()

    if last_game:
        next_id = last_game.id + 1
    else:
        next_id = 1

    prefix = get_random_string(length=2, allowed_chars='abcdefghijklmnopqrstuvwxyz')
    suffix = get_random_string(length=1, allowed_chars='abcdefghijklmnopqrstuvwxyz')

    final_code = f'{prefix}{next_id}{suffix}'

    try:
        new_game = Game.objects.create(
            code = final_code,
            state="room_not_started",
            creator=current_user,
        )

        return JsonResponse({"roomCode": new_game.code}, status=201)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

