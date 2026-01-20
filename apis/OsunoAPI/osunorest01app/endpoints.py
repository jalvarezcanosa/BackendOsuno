import json
import secrets
import bcrypt
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import User, UserSession, Game, GameCardInHand


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
def get_room_status(request, room_code):
    if request.method != 'GET':
        return JsonResponse({'error': 'HTTP method not supported'}, status=405)

    user = __get_request_user(request)
    if user is None:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        game = Game.objects.get(code=room_code)
    except Game.DoesNotExist:
        return JsonResponse({'error': 'Room not found'}, status=404)

    # Verificar que el usuario pertenece a la sala
    if game.creator != user and game.joined != user:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    # Determinar el estado de la sala
    if game.joined is None:
        status = "waiting"
    else:
        status = "gameStarted"

    return JsonResponse({"status": status}, status=200)

#