from django.contrib.auth.models import User
from django.db import models


class ScanHistory(models.Model):
    scan_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='scans')
    item_name = models.CharField(max_length=255)
    is_recyclable = models.BooleanField(default=False)
    cached_api_data = models.JSONField(null=True, blank=True)
    scanned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'scan_history'
        indexes = [
            models.Index(fields=['user']),
        ]

    def __str__(self):
        return f"{self.item_name} scanned by {self.user.username}"


class ScanAttempt(models.Model):
    """One row per request that reached the AI, successful or not. Powers the hourly rate limit."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='scan_attempts')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'scan_attempts'
        indexes = [
            models.Index(fields=['user', 'created_at']),
        ]

    def __str__(self):
        return f"attempt by {self.user.username} at {self.created_at:%Y-%m-%d %H:%M}"