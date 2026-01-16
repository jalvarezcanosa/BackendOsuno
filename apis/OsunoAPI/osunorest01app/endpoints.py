import json
import secrets
import bcrypt
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import User, UserSession, Game, GameCardInHand, GameDeckCard


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

#############################################################################
def __can_play_card(card_to_play, table_card):
    """
    Verifica si una carta puede jugarse sobre la carta de la mesa.
    Reglas: mismo color O mismo número
    """
    if table_card is None:
        return True

    # Extraer color y número de ambas cartas
    # Asumiendo formato: "blue4", "red7", etc.
    color_to_play = ''.join([c for c in card_to_play if c.isalpha()])
    number_to_play = ''.join([c for c in card_to_play if c.isdigit()])

    color_table = ''.join([c for c in table_card if c.isalpha()])
    number_table = ''.join([c for c in table_card if c.isdigit()])

    # Puede jugarse si coincide el color O el número
    return color_to_play == color_table or number_to_play == number_table


def __check_opponent_can_play(game, opponent):
    """
    Verifica si el oponente tiene alguna carta jugable
    """
    opponent_cards = GameCardInHand.objects.filter(game=game, player=opponent)

    for card_in_hand in opponent_cards:
        if __can_play_card(card_in_hand.card_code, game.table_card):
            return True

    return False


def __check_game_over(game, current_player):
    """
    Verifica las condiciones de game over:
    1. El jugador actual no tiene más cartas en mano (ganó)
    2. No hay cartas en el mazo Y el rival no puede jugar (ganó el jugador actual)
    """
    # Verificar si el jugador actual se quedó sin cartas
    current_player_cards = GameCardInHand.objects.filter(game=game, player=current_player).count()
    if current_player_cards == 0:
        return True, current_player

    # Verificar si no hay cartas en el mazo
    deck_cards = GameDeckCard.objects.filter(game=game).count()
    if deck_cards == 0:
        # Determinar quién es el oponente
        opponent = game.joined if current_player == game.creator else game.creator

        # Verificar si el oponente puede jugar
        if not __check_opponent_can_play(game, opponent):
            return True, current_player

    return False, None


@csrf_exempt
def play_card(request, room_code):
    if request.method != 'POST':
        return JsonResponse({'error': 'HTTP method not supported'}, status=405)

    # Autenticación
    user = __get_request_user(request)
    if user is None:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    # Parsear body
    try:
        body_json = json.loads(request.body)
        card_to_play = body_json['cardToPlay']
    except (json.JSONDecodeError, KeyError):
        return JsonResponse({"error": "Missing parameter"}, status=400)

    # Verificar que la sala existe
    try:
        game = Game.objects.get(code=room_code)
    except Game.DoesNotExist:
        return JsonResponse({'error': 'Room not found'}, status=404)

    # Verificar que el usuario pertenece a la sala
    if game.creator != user and game.joined != user:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    # Verificar que es el turno del jugador
    is_creator_turn = game.state == "creator_turn"
    is_users_turn = (is_creator_turn and user == game.creator) or (not is_creator_turn and user == game.joined)

    if not is_users_turn:
        return JsonResponse({'error': 'Forbidden - Not your turn'}, status=403)

    # Verificar que el jugador tiene esa carta en la mano
    try:
        card_in_hand = GameCardInHand.objects.get(game=game, player=user, card_code=card_to_play)
    except GameCardInHand.DoesNotExist:
        return JsonResponse({'error': 'Forbidden - Card not in your hand'}, status=403)

    # Verificar que la carta puede jugarse
    if not __can_play_card(card_to_play, game.table_card):
        return JsonResponse({'error': 'Forbidden - Card cannot be played'}, status=403)

    # JUGAR LA CARTA
    # 1. Remover la carta de la mano del jugador
    card_in_hand.delete()

    # 2. Actualizar la carta en la mesa
    game.table_card = card_to_play

    # 3. Cambiar el turno
    if is_creator_turn:
        game.state = "joined_turn"
    else:
        game.state = "creator_turn"

    # 4. Verificar condiciones de game over
    is_game_over, winner = __check_game_over(game, user)

    if is_game_over:
        game.state = "finished"
        game.winner = winner

        # Actualizar estadísticas del ganador
        winner.games_won += 1
        winner.games_played += 1
        winner.save()

        # Actualizar estadísticas del perdedor
        loser = game.joined if winner == game.creator else game.creator
        loser.games_played += 1
        loser.save()

    game.save()

    return JsonResponse({
        "success": True,
        "tableCard": game.table_card,
        "gameState": game.state,
        "isGameOver": is_game_over,
        "winner": winner.username if is_game_over else None
    }, status=200)