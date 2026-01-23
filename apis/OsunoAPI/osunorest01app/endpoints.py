import json
import bcrypt
from django.http import JsonResponse
from django.utils.crypto import get_random_string
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Min
from .models import User, UserSession, Game, GameDeckCard, GameCardInHand


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


def __check_playable_cards(hand_cards, top_card_code):
    """Verifica si hay cartas jugables en la mano"""
    if not hand_cards or not top_card_code:
        return False

    top_color = top_card_code[0] if len(top_card_code) > 0 else None
    top_value = top_card_code[1:] if len(top_card_code) > 1 else None

    for card in hand_cards:
        card_code = card.card_code
        card_color = card_code[0] if len(card_code) > 0 else None
        card_value = card_code[1:] if len(card_code) > 1 else None

        if card_color == 'W':  # Comodines
            return True
        if card_color == top_color or card_value == top_value:
            return True

    return False


def __determine_winner(creator, joined, game):
    """Determina el ganador basado en quien tiene menos cartas"""
    creator_cards = GameCardInHand.objects.filter(game=game, player=creator).count()
    joined_cards = GameCardInHand.objects.filter(game=game, player=joined).count()

    if creator_cards < joined_cards:
        return creator
    elif joined_cards < creator_cards:
        return joined
    else:
        return creator


def __is_card_playable(card_code, top_card_code):
    """Verifica si una carta específica puede jugarse"""
    if not card_code or not top_card_code:
        return False

    card_color = card_code[0] if len(card_code) > 0 else None
    card_value = card_code[1:] if len(card_code) > 1 else None

    top_color = top_card_code[0] if len(top_card_code) > 0 else None
    top_value = top_card_code[1:] if len(top_card_code) > 1 else None

    # Comodines siempre pueden jugarse
    if card_color == 'W':
        return True

    # Mismo color o mismo valor
    if card_color == top_color or card_value == top_value:
        return True

    return False


# ================= ENDPOINTS =================

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

    if game.creator != user and game.joined != user:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    if game.joined is None:
        status = "waiting"
    else:
        status = "gameStarted"

    return JsonResponse({"status": status}, status=200)


@csrf_exempt
def draw_card(request, room_code):
    """
    POST /game/{room_code}/deck
    Robar una carta del mazo
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'HTTP method not supported'}, status=405)

    user = __get_request_user(request)
    if user is None:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        game = Game.objects.get(code=room_code)
    except Game.DoesNotExist:
        return JsonResponse({'error': 'Room not found'}, status=404)

    if game.creator != user and game.joined != user:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    is_creator = (game.creator == user)

    any_deck_card = GameDeckCard.objects.filter(game=game).first()
    if any_deck_card is None:
        return JsonResponse({'error': 'Game not initialized'}, status=400)

    is_creator_turn = any_deck_card.is_creator_turn

    if is_creator != is_creator_turn:
        return JsonResponse({'error': 'Not your turn'}, status=403)

    # Obtener cartas disponibles en el mazo
    deck_cards = GameDeckCard.objects.filter(game=game).order_by('initial_position')
    cards_in_hands = GameCardInHand.objects.filter(game=game).values_list('card_code', flat=True)
    available_cards = deck_cards.exclude(card_code__in=cards_in_hands)

    if not available_cards.exists():
        return JsonResponse({'error': 'No hay cartas en el mazo'}, status=403)

    card_to_draw = available_cards.first()

    GameCardInHand.objects.create(
        card_code=card_to_draw.card_code,
        player=user,
        game=game
    )

    remaining_cards = available_cards.exclude(card_code=card_to_draw.card_code)

    if not remaining_cards.exists():
        game_state = json.loads(game.state) if game.state else {}
        top_card_code = game_state.get('top_card', '')
        current_player_cards = GameCardInHand.objects.filter(game=game, player=user)
        has_playable = __check_playable_cards(current_player_cards, top_card_code)

        if not has_playable:
            rival = game.joined if is_creator else game.creator
            rival_cards = GameCardInHand.objects.filter(game=game, player=rival)
            rival_has_playable = __check_playable_cards(rival_cards, top_card_code)

            if rival_has_playable:
                GameDeckCard.objects.filter(game=game).update(
                    is_creator_turn=not is_creator_turn
                )
            else:
                winner = __determine_winner(game.creator, game.joined, game)
                winner.games_won += 1
                winner.games_played += 1
                winner.save()

                loser = game.joined if winner == game.creator else game.creator
                loser.games_played += 1
                loser.save()

                game_state['status'] = 'finished'
                game_state['winner'] = winner.username
                game_state['reason'] = 'No quedan cartas jugables'
                game.state = json.dumps(game_state)
                game.save()

                return JsonResponse({
                    'message': 'Juego terminado',
                    'winner': winner.username,
                    'reason': 'No quedan cartas jugables'
                }, status=200)

    return JsonResponse({
        'message': 'Carta robada exitosamente',
        'cards_in_deck': remaining_cards.count()
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

    while True:
        room_code = get_random_string(length=3, allowed_chars='ABCDEFGHIJKLMNOPQRSTUVWXYZ')
        if not Game.objects.filter(code=room_code).exists():
            break

    try:
        new_game = Game.objects.create(
            code=room_code,
            state="{}",
            creator=current_user,
        )
        return JsonResponse({"roomCode": new_game.code}, status=201)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def play_card(request, room_code):
    """
    POST /game/{room_code}/card
    Body: {"card_code": "R5", "color": "R"} (color opcional para comodines)
    Jugar una carta
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'HTTP method not supported'}, status=405)

    user = __get_request_user(request)
    if user is None:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        body_json = json.loads(request.body)
        card_code = body_json['card_code']
    except (json.JSONDecodeError, KeyError):
        return JsonResponse({"error": "Missing parameter"}, status=400)

    try:
        game = Game.objects.get(code=room_code)
    except Game.DoesNotExist:
        return JsonResponse({'error': 'Room not found'}, status=404)

    if game.creator != user and game.joined != user:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    game_state = json.loads(game.state) if game.state else {}
    is_creator = (game.creator == user)

    any_deck_card = GameDeckCard.objects.filter(game=game).first()
    if any_deck_card is None:
        return JsonResponse({'error': 'Game not initialized'}, status=400)

    is_creator_turn = any_deck_card.is_creator_turn

    if is_creator != is_creator_turn:
        return JsonResponse({'error': 'Not your turn'}, status=403)

    # Verificar que el jugador tiene la carta
    try:
        card_in_hand = GameCardInHand.objects.get(
            game=game,
            player=user,
            card_code=card_code
        )
    except GameCardInHand.DoesNotExist:
        return JsonResponse({'error': 'Card not in hand'}, status=400)

    # Verificar que la carta puede jugarse
    top_card_code = game_state.get('top_card', '')
    if not __is_card_playable(card_code, top_card_code):
        return JsonResponse({'error': 'Card cannot be played'}, status=400)

    # Jugar la carta (removerla de la mano)
    card_in_hand.delete()

    # Actualizar carta superior
    if card_code[0] == 'W':
        game_state['top_card'] = card_code[1:]
    else:
        game_state['top_card'] = card_code

    # Verificar si el jugador ganó (no tiene más cartas)
    remaining_cards = GameCardInHand.objects.filter(game=game, player=user).count()
    if remaining_cards == 0:

        ''' Toda esta parte que tengo comentada va a fallar porque no existen estos campos en BBDD
        user.games_won += 1
        user.games_played += 1
        user.save()

        rival = game.joined if is_creator else game.creator
        rival.games_played += 1
        rival.save()'''

        ##Si el creador ganó status = creator_won si ganó el joined status = joined_won
        game_state['status'] = 'finished'
        game_state['winner'] = user.username
        ##Reason me sobra muchísimo
        game_state['reason'] = 'No cards left'
        game.state = json.dumps(game_state)
        game.save()

        return JsonResponse({
            'message': 'You won!',
            'winner': user.username
        }, status=200)

    # Cambiar turno
    GameDeckCard.objects.filter(game=game).update(
        is_creator_turn=not is_creator_turn
    )

    game.state = json.dumps(game_state)
    game.save()

    return JsonResponse({
        'message': 'Card played successfully',
        'top_card': game_state['top_card']
    }, status=200)


@csrf_exempt
def get_hand(request, room_code):
    """
    GET /game/{room_code}/hand
    Obtener las cartas en la mano del jugador
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'HTTP method not supported'}, status=405)

    user = __get_request_user(request)
    if user is None:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        game = Game.objects.get(code=room_code)
    except Game.DoesNotExist:
        return JsonResponse({'error': 'Room not found'}, status=404)

    if game.creator != user and game.joined != user:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    # Obtener cartas del jugador
    hand_cards = GameCardInHand.objects.filter(game=game, player=user)
    cards_list = [card.card_code for card in hand_cards]

    return JsonResponse({
        'cards': cards_list,
        'count': len(cards_list)
    }, status=200)


@csrf_exempt
def get_game_state(request, room_code):
    """
    GET /game/{room_code}/state
    Obtener el estado actual del juego (polling)
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'HTTP method not supported'}, status=405)

    user = __get_request_user(request)
    if user is None:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        game = Game.objects.get(code=room_code)
    except Game.DoesNotExist:
        return JsonResponse({'error': 'Room not found'}, status=404)

    if game.creator != user and game.joined != user:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    game_state = json.loads(game.state) if game.state else {}

    # Determinar de quién es el turno
    any_deck_card = GameDeckCard.objects.filter(game=game).first()
    if any_deck_card:
        is_creator_turn = any_deck_card.is_creator_turn
        is_my_turn = (game.creator == user and is_creator_turn) or (game.joined == user and not is_creator_turn)
    else:
        is_my_turn = False

    # Contar cartas de cada jugador
    creator_card_count = GameCardInHand.objects.filter(game=game, player=game.creator).count()
    joined_card_count = GameCardInHand.objects.filter(game=game, player=game.joined).count() if game.joined else 0

    # Contar cartas en el mazo
    cards_in_hands = GameCardInHand.objects.filter(game=game).values_list('card_code', flat=True)
    deck_cards = GameDeckCard.objects.filter(game=game).exclude(card_code__in=cards_in_hands)

    return JsonResponse({
        'top_card': game_state.get('top_card', ''),
        'is_my_turn': is_my_turn,
        'my_card_count': creator_card_count if game.creator == user else joined_card_count,
        'opponent_card_count': joined_card_count if game.creator == user else creator_card_count,
        'deck_count': deck_cards.count(),
        'game_status': game_state.get('status', 'playing'),
        'winner': game_state.get('winner', None)
    }, status=200)


@csrf_exempt
def get_playable_cards(request, room_code):
    """
    GET /game/{room_code}/playable
    Obtener las cartas jugables de la mano
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'HTTP method not supported'}, status=405)

    user = __get_request_user(request)
    if user is None:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        game = Game.objects.get(code=room_code)
    except Game.DoesNotExist:
        return JsonResponse({'error': 'Room not found'}, status=404)

    if game.creator != user and game.joined != user:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    game_state = json.loads(game.state) if game.state else {}
    top_card_code = game_state.get('top_card', '')

    # Obtener cartas del jugador
    hand_cards = GameCardInHand.objects.filter(game=game, player=user)

    playable_cards = []
    for card in hand_cards:
        if __is_card_playable(card.card_code, top_card_code):
            playable_cards.append(card.card_code)

    return JsonResponse({
        'playable_cards': playable_cards,
        'count': len(playable_cards)
    }, status=200)