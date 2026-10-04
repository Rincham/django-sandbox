from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required
from django.utils.decorators import method_decorator


@method_decorator(login_not_required, name='dispatch')
class LoginView(auth_views.LoginView):
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True


@method_decorator(login_not_required, name='dispatch')
class LogoutView(auth_views.LogoutView):
    pass
