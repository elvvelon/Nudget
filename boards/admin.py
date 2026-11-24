from django.contrib import admin

from .models import Board, BoardMember, Card, CardActivity, Column, Subtask

admin.site.register([Board, BoardMember, Column, Card, Subtask, CardActivity])
