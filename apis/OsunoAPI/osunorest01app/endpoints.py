import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Min
from .models import User, UserSession, Game, GameDeckCard, GameCardInHand


def __get_request_user(request):
    header_token = request.headers.get('Session', None)
    if header_token is None:
        return None
    try:
        db_session = UserSession.objects.get(token=header_token)
        return db_session.user
    except UserSession.DoesNotExist:
        return None


def __check_playable_cards(hand_cards, top_card_code, game):
    """
    Verifica si hay cartas jugables en la mano
    """
    # Obtener información de la carta superior
    top_color = top_card_code[0] if len(top_card_code) > 0 else None
    top_value = top_card_code[1:] if len(top_card_code) > 1 else None

    for card in hand_cards:
        card_color = card.card_code[0] if len(card.card_code) > 0 else None
        card_value = card.card_code[1:] if len(card.card_code) > 1 else None

        # Comodines (W = wild)
        if card_color == 'W':
            return True

        # Mismo color o mismo valor
        if card_color == top_color or card_value == top_value:
            return True

    return False


def __determine_winner(creator, joined, game):
    """
    Determina el ganador basado en quien tiene menos cartas
    """
    creator_cards = GameCardInHand.objects.filter(game=game, player=creator).count()
    joined_cards = GameCardInHand.objects.filter(game=game, player=joined).count()

    if creator_cards < joined_cards:
        return creator
    elif joined_cards < creator_cards:
        return joined
    else:
        return creator  # En empate gana el creador


@csrf_exempt
def draw_card(request, room_code):
    """
    POST /game/{room_code}/deck
    Endpoint para robar una carta del mazo
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'HTTP method not supported'}, status=405)

    # Obtener usuario desde el token
    user = __get_request_user(request)
    if user is None:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    # Verificar que el juego existe
    try:
        game = Game.objects.get(code=room_code)
    except Game.DoesNotExist:
        return JsonResponse({'error': 'Room not found'}, status=404)

    # Verificar que el usuario pertenece al juego
    if game.creator != user and game.joined != user:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    # Verificar que el juego está en curso
    game_state = json.loads(game.state) if game.state else {}

    # Verificar que es el turno del jugador
    is_creator = (game.creator == user)

    # Obtener el turno actual desde GameDeckCard
    try:
        any_deck_card = GameDeckCard.objects.filter(game=game).first()
        if any_deck_card is None:
            return JsonResponse({'error': 'Game not initialized'}, status=400)

        is_creator_turn = any_deck_card.is_creator_turn
    except GameDeckCard.DoesNotExist:
        return JsonResponse({'error': 'Game not initialized'}, status=400)

    if is_creator != is_creator_turn:
        return JsonResponse({'error': 'Not your turn'}, status=403)

    # Verificar si hay cartas en el mazo (cartas sin asignar a jugadores)
    deck_cards = GameDeckCard.objects.filter(game=game).order_by('initial_position')

    # Obtener cartas que no están en manos de jugadores
    cards_in_hands = GameCardInHand.objects.filter(game=game).values_list('card_code', flat=True)
    available_cards = deck_cards.exclude(card_code__in=cards_in_hands)

    if not available_cards.exists():
        return JsonResponse({'error': 'No hay cartas en el mazo'}, status=403)

    # Robar la primera carta disponible
    card_to_draw = available_cards.first()

    # Añadir carta a la mano del jugador
    new_card = GameCardInHand(
        card_code=card_to_draw.card_code,
        player=user,
        game=game
    )
    new_card.save()

    # Verificar si quedan cartas en el mazo después de robar
    remaining_cards = available_cards.exclude(card_code=card_to_draw.card_code)

    if not remaining_cards.exists():
        # No quedan cartas en el mazo
        # Obtener la carta superior (última jugada)
        top_card_code = game_state.get('top_card', '')

        # Obtener cartas del jugador actual
        current_player_cards = GameCardInHand.objects.filter(game=game, player=user)
        has_playable = __check_playable_cards(current_player_cards, top_card_code, game)

        if not has_playable:
            # El jugador actual NO tiene cartas jugables
            # Obtener el rival
            rival = game.joined if is_creator else game.creator
            rival_cards = GameCardInHand.objects.filter(game=game, player=rival)
            rival_has_playable = __check_playable_cards(rival_cards, top_card_code, game)

            if rival_has_playable:
                # El rival SÍ tiene cartas jugables, cambiar turno
                GameDeckCard.objects.filter(game=game).update(
                    is_creator_turn=not is_creator_turn
                )
            else:
                # Nadie tiene cartas jugables, GAME OVER
                winner = __determine_winner(game.creator, game.joined, game)

                # Actualizar estadísticas
                winner.games_won += 1
                winner.games_played += 1
                winner.save()

                loser = game.joined if winner == game.creator else game.creator
                loser.games_played += 1
                loser.save()

                # Actualizar estado del juego
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

    # El turno NO cambia después de robar carta
    # El cliente debe hacer poll para obtener su nueva mano
    return JsonResponse({
        'message': 'Carta robada exitosamente',
        'cards_in_deck': remaining_cards.count() if remaining_cards.exists() else 0
    }, status=200)