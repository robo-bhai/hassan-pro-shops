"""
Custom Storage for Termux (Android)
Bypasses fcntl.flock() which is not supported on Android kernel
"""
import os
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class TermuxFileSystemStorage(FileSystemStorage):
    """
    Custom FileSystemStorage that works on Termux (Android).
    Django's default FileSystemStorage uses fcntl.flock() for file locking,
    which Android kernel does not support. This class skips file locking.
    """
    
    def _save(self, name, content):
        """Save file WITHOUT file locking"""
        full_path = self.path(name)
        
        # Create directory if not exists
        directory = os.path.dirname(full_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        
        # If file exists, get unique name
        if os.path.exists(full_path):
            name = self.get_available_name(name)
            full_path = self.path(name)
        
        # Write file directly without locking
        with open(full_path, 'wb+') as destination:
            for chunk in content.chunks():
                destination.write(chunk)
        
        return name
    
    def exists(self, name):
        """Safe exists check"""
        try:
            return super().exists(name)
        except Exception:
            return False
