import json
import secrets

import bcrypt
from django.http import JsonResponse

from apis.OsunoAPI.osunorest01app.models import UserSession


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

    ##if User.objects.filter(username=username_json).exists():
        return JsonResponse({"error": "User already exists"}, status=409)##

    try:
        db_user = User.objects.get(username=username_json)
    except User.DoesNotExist:
        return JsonResponse({"error": "User not found"}, status=404)

    if bcrypt.checkpw(password_json.encode('utf8'), db_user.encrypted_password.encode('utf8')):
        random_token = secrets.token_hex(10)
        session = UserSession(person=db_user, token=random_token)
        session.save()
        return JsonResponse({"Created"}, status=201)
    else:
        return JsonResponse({"error": "Password not valid"}, status=401)

def __get_request_user(request):
    header_token = request.headers.get('Api-Session-Token', None)
    if header_token is None:
        return None
    try:
        db_session = UserSession.objects.get(token=header_token)
        return db_session.user
    except UserSession.DoesNotExist:
        return None