import json
import secrets
import bcrypt
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import User, UserSession

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
        {"user_session_token": token}, status=201)