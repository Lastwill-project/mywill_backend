from django.core.mail import send_mail

from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Sentence
from .serializers import SentenceSerializer
from lastwill.permissions import IsStaff, CreateOnly
from lastwill.settings import UNBLOCKING_EMAIL, DEFAULT_FROM_EMAIL


class SentenceViewSet(ModelViewSet):
    permission_classes = (IsStaff | CreateOnly,)
    queryset = Sentence.objects.all()
    serializer_class = SentenceSerializer


@api_view(http_method_names=['POST'])
def send_unblocking_info(request):
    name = request.data.get('name')
    email = request.data.get('email')
    message = request.data.get('message')
    send_mail(
        'Feedback form',
        {'name': name, 'email': email, 'message': message},
        DEFAULT_FROM_EMAIL,
        UNBLOCKING_EMAIL
    )
    return Response({'result': 'ok'})
