from django.db import models
from django.contrib.auth.models import User

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