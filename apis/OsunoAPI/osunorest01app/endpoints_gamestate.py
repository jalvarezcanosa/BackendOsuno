from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Game, GameCardInHand

@csrf_exempt
def get_game_state(request, code):
    if request.method != 'GET':
        return JsonResponse({'error': 'HTTP method not supported'}, status=405)

    user = __get_request_user(request)
    if user is None:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        game = Game.objects.get(code=code)
    except Game.DoesNotExist:
        return JsonResponse({'error': 'Game not found'}, status=404)

    if user != game.creator and user != game.joined:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    creator_hand_qs = GameCardInHand.objects.filter(game=game, player=game.creator)
    joined_hand_qs = GameCardInHand.objects.filter(game=game, player=game.joined)

    creator_hand = [c.card_code for c in creator_hand_qs]
    joined_hand = [c.card_code for c in joined_hand_qs]

    if game.state == "room_not_started":
        table_card = "none"
        current_turn = "creator"
    else:
        table_card = "none"
        total_played = 10 - len(creator_hand) - len(joined_hand)
        current_turn = "creator" if total_played % 2 == 0 else "joined"

    deck_empty = False
    game_finished = "no"
    winner = None

    if deck_empty:
        if len(creator_hand) < len(joined_hand):
            winner = game.creator
            game_finished = "youWon" if user == game.creator else "youLost"
        elif len(creator_hand) > len(joined_hand):
            winner = game.joined
            game_finished = "youWon" if user == game.joined else "youLost"
        else:
            winner = None
            game_finished = "draw"

    if winner:
        winner.games_won += 1
        winner.save()
    game.creator.games_played += 1
    game.creator.save()
    if game.joined:
        game.joined.games_played += 1
        game.joined.save()

    response = {
        "hands": {
            "creator": creator_hand,
            "joined": joined_hand
        },
        "tableCard": table_card,
        "currentTurn": current_turn,
        "gameFinished": game_finished
    }

    return JsonResponse(response, status=200)