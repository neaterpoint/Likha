from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST


def _safe_next(request):
    """Return the ?next= target only if it points back to this site."""
    target = request.POST.get('next') or request.GET.get('next') or ''
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return ''


def login_view(request):
    if request.user.is_authenticated:
        return redirect(_safe_next(request) or 'home:home')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            return redirect(_safe_next(request) or 'home:home')
        messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm()

    return render(request, 'login/login.html', {'form': form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect('login:login')