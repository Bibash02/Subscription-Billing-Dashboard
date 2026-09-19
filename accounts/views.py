from django.shortcuts import render
from .serializers import RegisterSerializer, UserProfileSerializer, ChangePasswordSerializer
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import generics, permissions, status

# Create your views here.
class RegisterAPIView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

class MeAPIView(generics.RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

class ChangePasswordAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ChangePasswordSerializer

    def post(self, request):
        serializer = ChangePasswordSerializer(data = request.data, context = {'request': request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data['new_password'])
        request.user.save(update_fields = ['password'])
        return Response({'detail': 'Password updated.'}, status=status.HTTP_200_OK)