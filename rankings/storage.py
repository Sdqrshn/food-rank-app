import cloudinary
import cloudinary.uploader
import cloudinary.utils
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


@deconstructible
class CloudinaryStorage(Storage):
    def _save(self, name, content):
        content.seek(0)
        result = cloudinary.uploader.upload(content, folder="food-ranker")
        return f"{result['public_id']}.{result['format']}"

    def exists(self, name):
        return False

    def url(self, name):
        return cloudinary.utils.cloudinary_url(
            name, secure=True, width=1000, crop="limit", quality="auto", fetch_format="auto"
        )[0]

    def delete(self, name):
        cloudinary.uploader.destroy(name.rsplit(".", 1)[0])