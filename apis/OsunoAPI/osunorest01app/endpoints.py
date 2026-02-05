import json
import random
import secrets
from idlelib.rpc import request_queue

import bcrypt
from django.db import transaction
from django.http import JsonResponse
from django.utils.crypto import get_random_string
from django.views.decorators.csrf import csrf_exempt
from osunorest01app.models import User, UserSession, Game, GameDeckCard, GameCardInHand


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
        return JsonResponse({'error': 'Invalid token'}, status=401)

    # Contar sólo partidas finalizadas
    finished_states = ['creator_won', 'joined_won', 'draw']

    games_won = Game.objects.filter(creator=user, state='creator_won').count()
    games_won += Game.objects.filter(joined=user, state='joined_won').count()

    games_played = Game.objects.filter(creator=user, state__in=finished_states).count()
    games_played += Game.objects.filter(joined=user, state__in=finished_states).count()

    return JsonResponse({
        "username": user.username,
        "gamesWon": games_won,
        "gamesPlayed": games_played
    }, status=200)


@csrf_exempt
def create_room(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'HTTP method not supported'}, status=400)

    current_user = __get_request_user(request)
    if current_user is None:
        return JsonResponse({'error': 'Invalid token'}, status=401)

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


@csrf_exempt
def join_room(request, room_code):
    if request.method != 'POST':
        return JsonResponse({'error': 'HTTP method not supported'}, status=405)

    current_user = __get_request_user(request)
    if current_user is None:
        return JsonResponse({'error': 'Invalid token'}, status=401)

    try:
        game = Game.objects.get(code=room_code)
    except Game.DoesNotExist:
        return JsonResponse({'error': 'Game not found'}, status=404)

    if game.creator == current_user:
        return JsonResponse({'error': 'You cannot join your own game'}, status=400)

    if game.joined is not None:
        return JsonResponse({'error': 'Room is already full'}, status=409)

    try:
        with transaction.atomic():
            colors = ['R', 'G', 'B', 'Y']
            deck = []

            for color in colors:
                for num in range(0, 10):
                    card_code = f"{color}{num}"
                    deck.append(card_code)
            random.shuffle(deck)

            hand_creator = deck[:7]
            hand_joiner = deck[7:14]
            first_card_in_table = deck[14]
            remaining_deck = deck[15:]

            card_in_hand = []

            for card in hand_creator:
                card_in_hand.append(GameCardInHand(
                    card_code = card,
                    player = game.creator,
                    game = game
                ))

            for card in hand_joiner:
                card_in_hand.append(GameCardInHand(
                    card_code = card,
                    player = current_user,
                    game = game
                ))

            GameCardInHand.objects.bulk_create(card_in_hand)

            deck_objs = []
            for i, card in enumerate(remaining_deck):
                deck_objs.append(GameDeckCard(
                    game = game,
                    card_code = card,
                    initial_position = i
                ))

            GameDeckCard.objects.bulk_create(deck_objs)

            game.joined = current_user
            game.state = "in_progress"
            game.card_in_table = first_card_in_table
            game.save()

        return JsonResponse({'message': 'joined'}, status=200)

    except Exception as e:
        return JsonResponse({'error': f'Error creating game deck: {str(e)}'}, status=500)


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


@csrf_exempt
def handle_room(request, room_code):
    if request.method == 'GET':
        return get_room_status(request,room_code)
    elif request.method == 'POST':
        return join_room(request, room_code)
    else:
        return JsonResponse({'error': 'Method not supported'}, status=405)

@csrf_exempt
def _parse_card(card_code: str):
    if not card_code or len(card_code) < 2:
        return ('', '')
    c = card_code[0].lower()
    if c not in ('r', 'g', 'b', 'y'):
        return ('', '')
    num = card_code[1:]
    if not num.isdigit():
        return ('', '')
    return (c, num)


@csrf_exempt
def play_card(request, room_code):
    if request.method != 'POST':
        return JsonResponse({'error': 'HTTP method not supported'}, status=405)

    user = __get_request_user(request)
    if user is None:
        return JsonResponse({'error': 'Invalid token'}, status=401)

    try:
        game = Game.objects.get(code=room_code)
    except Game.DoesNotExist:
        return JsonResponse({'error': 'Room not found'}, status=404)

    # Verificar que el usuario pertenece a la sala
    if game.creator != user and game.joined != user:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    # verificar que la sala ya ha empezado
    if game.joined is None:
        return JsonResponse({'error': 'Game has no opponent yet'}, status=403)

    # Verificar que el usuario es el turno actual
    is_creator_turn = game.is_creator_turn
    if is_creator_turn and game.creator != user:
        return JsonResponse({'error': 'Not your turn'}, status=403)
    if (not is_creator_turn) and game.joined != user:
        return JsonResponse({'error': 'Not your turn'}, status=403)

    # Decidir ganador en mazo vacío
    if not GameDeckCard.objects.filter(game=game).exists():
        creator_count = GameCardInHand.objects.filter(game=game, player=game.creator).count()
        joined_count = GameCardInHand.objects.filter(game=game, player=game.joined).count()

        if creator_count < joined_count:
            game.state = 'creator_won'
        elif joined_count < creator_count:
            game.state = 'joined_won'
        else:
            game.state = 'draw'

        game.save()
        return JsonResponse({'message': 'game finished, deck empty', 'state': game.state}, status=201)

    # Parsear request body
    try:
        body = json.loads(request.body)
        card_to_play = body['cardToPlay']
    except (json.JSONDecodeError, KeyError):
        return JsonResponse({"error": "Missing parameter"}, status=400)

    # Verificar que el usuario tiene la carta en su mano
    has_card_qs = GameCardInHand.objects.filter(game=game, player=user, card_code=card_to_play)
    if not has_card_qs.exists():
        return JsonResponse({'error': 'You do not have that card'}, status=403)

    # Verificar que es jugable (color o número)
    table_card = (game.card_in_table or '').lower()
    if table_card in ('', 'none'):
        valid_play = True
    else:
        table_color, table_num = _parse_card(table_card)
        play_color, play_num = _parse_card(card_to_play.lower())
        valid_play = (play_color != '') and ((play_color == table_color) or (play_num == table_num))

    if not valid_play:
        return JsonResponse({'error': 'Card does not match color or number'}, status=403)

    try:
        with transaction.atomic():
            # Quitar carta de mano
            has_card_qs.delete()

            # Actualizar carta en mesa y turno
            game.card_in_table = card_to_play
            game.is_creator_turn = not game.is_creator_turn

            # Verificar ganador por 0 cartas en mano
            remaining = GameCardInHand.objects.filter(game=game, player=user).count()
            if remaining == 0:
                if user == game.creator:
                    game.state = 'creator_won'
                else:
                    game.state = 'joined_won'
            game.save()

        return JsonResponse({'message': 'card played'}, status=201)
    except Exception as e:
        return JsonResponse({'error': f'Error playing card: {str(e)}'}, status=500)

@csrf_exempt
def steal_card(request, room_code):
    if request.method != 'POST':
        return JsonResponse({'error': 'HTTP method not supported'}, status=405)

    current_user = __get_request_user(request)
    if current_user is None:
        return JsonResponse({'error': 'Invalid token'}, status=401)

    try:
        game = Game.objects.get(code=room_code)
    except Game.DoesNotExist:
        return JsonResponse({'error': 'Game not found'}, status=404)

    if game.creator != current_user and game.joined != current_user:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    if game.is_creator_turn:
        player_turn = game.creator
    else:
        player_turn = game.joined

    if current_user != player_turn:
        return JsonResponse({'error': 'Not your turn'}, status=403)

    top_value = game.card_in_table[1:]
    top_color = game.card_in_table[0]

    try:
        with transaction.atomic():

            while(True):
                deck_cards = GameDeckCard.objects.filter(game=game).order_by('initial_position')

                if not deck_cards.exists():
                    creator_count = GameCardInHand.objects.filter(game=game, player=game.creator).count()
                    joined_count = GameCardInHand.objects.filter(game=game, player=game.joined).count()

                    if creator_count < joined_count:
                        game.state = 'creator_won'
                    elif joined_count < creator_count:
                        game.state = 'joined_won'
                    else:
                        game.state = 'draw'

                    game.save()

                    return JsonResponse({
                        'message': 'Game Over',
                        'state': game.state,
                        'scores': {'creator': creator_count, 'joined': joined_count}
                    }, status=201)

                else:
                    card_to_steal = deck_cards.first()
                    new_card_code = card_to_steal.card_code

                    GameCardInHand.objects.create(
                        game=game,
                        player=current_user,
                        card_code=new_card_code
                    )

                    card_to_steal.delete()

                    new_value = new_card_code[1:]
                    new_color = new_card_code[0]

                    if new_value == top_value or new_color == top_color:
                        return JsonResponse({'message': 'Playable card stolen'})

                    game.save()

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
#endpoint asociado a GH_7
@csrf_exempt
def get_game_state(request, room_code):
    #verifica que el metodo sea GET
    if request.method != 'GET':
            return JsonResponse({'error': 'HTTP method not supported'}, status=405)

    #valida el token de sesion
    current_user = __get_request_user(request)

    if current_user is None:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    #busca la partida
    try:
        game = Game.objects.get(code=room_code)

    except Game.DoesNotExist:
        return JsonResponse({'error': 'Game not found'}, status=404)

    #verifica que el usuario pertenece a la partida
    if game.creator != current_user and game.joined != current_user:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    ##obtiene las cartas de la mano del usuario
    # .values_list('card_code', flat=True) extrae solo los códigos de las cartas
    # flat=True convierte [(carta1,), (carta2,)] en [carta1, carta2]
    user_cards = GameCardInHand.objects.filter(
        game = game,
        player = current_user
    ).values_list('card_code',flat=True)

    #convertir el QuerrySet de Django a una lista en Phyton
    #ej: ['Red4','Green3']
    your_hand = list(user_cards)

   ###determinar la carta en la mesa
    table_card = game.card_in_table if game.card_in_table else "none"

    deck_cards_count = GameDeckCard.objects.filter(game=game).count()

    if current_user == game.creator:
        rival_cards_count = GameCardInHand.objects.filter(game=game, player=game.joined).count()
    elif current_user == game.joined:
        rival_cards_count = GameCardInHand.objects.filter(game=game, player=game.creator).count()

    #determinar si es tu turno
    is_creator_turn =(current_user == game.creator and game.is_creator_turn)

    is_joined_turn = (current_user == game.joined and not game.is_creator_turn)

    is_your_turn = is_creator_turn or is_joined_turn

    #determinar el estado del juego
    game_finished = "no"

    if game.state == "creator_won":
        game_finished = "youWon" if current_user == game.creator else "youLost"
    elif game.state == "joined_won":
        game_finished = "youWon" if current_user == game.joined else "youLost"
    elif game.state == "draw":
        game_finished = "draw"

    response_data = {
        "yourHand": your_hand,
        "rivalHand": rival_cards_count,
        "tableCard": table_card,
        "cardsLeftInDeck": deck_cards_count,
        "isYourTurn": is_your_turn,
        "gameFinished": game_finished,
    }
    return JsonResponse(response_data, status=200)
