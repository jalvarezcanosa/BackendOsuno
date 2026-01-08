from django.db import models

class User(models.Model):
    username = models.CharField(max_length=220)
    encrypted_password = models.CharField(max_length=120)

class UserSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    token = models.CharField(unique=True, max_length=35)

class Room(models.Model):
    code = models.CharField(unique=True, max_length=10)

class Game(models.Model):
    state = models.CharField(max_length=220) #room_not_started, ...
    creator = models.ForeignKey(User, on_delete=models.CASCADE)
    join = models.ForeignKey(Room, on_delete=models.CASCADE)

class GameDeckCard(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE)
    card_code = models.CharField
    initial_position = models.IntegerField()
    is_creator_turn = models.BooleanField(default=True)

class GameCardInHand(models.Model):
    card_code = models.CharField(unique=True, max_length=10)
    player = models.ForeignKey(User, on_delete=models.CASCADE)
    game = models.ForeignKey(Game, on_delete=models.CASCADE)
