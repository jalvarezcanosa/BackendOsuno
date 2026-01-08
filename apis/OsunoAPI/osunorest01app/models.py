from django.db import models

class User(models.Model):
    username = models.CharField(max_length=220)
    encrypted_password = models.CharField(max_length=120)

class UserSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    token = models.CharField(unique=True, max_length=35)


