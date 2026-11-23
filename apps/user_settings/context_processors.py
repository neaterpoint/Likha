from .models import UserSettings


def theme(request):
    """Expose the signed-in user's theme as {{ user_theme }} ('light' or 'dark')."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"user_theme": "light"}
    value = request.session.get("theme")
    if value not in ("light", "dark"):
        value = UserSettings.objects.filter(user=user).values_list("theme", flat=True).first() or "light"
        request.session["theme"] = value
    return {"user_theme": value}